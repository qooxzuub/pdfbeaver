# src/pdfbeaver/editor.py

"""Module: pdfbeaver.editor

This module contains functionality for processing and modifying
content streams in PDF files. It provides the `StreamEditor` class
that allows for the manipulation of PDF operators and operands during
the content stream parsing process.
"""


import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    Union,
    runtime_checkable,
)

import numpy as np
import pikepdf
from pdfminer.pdftypes import PDFStream
from pikepdf import Array, Operator

from .utils.pdf_geometry import extract_text_position

if TYPE_CHECKING:
    from pikepdf.models.image import PdfInlineImage

    from ..engines.state_tracker import TargetStateTracker

logger = logging.getLogger(__name__)

# --- Strict Type Definitions ---
NormalizedOperand = Union[
    bool,
    int,
    float,
    Decimal,
    pikepdf.Name,
    pikepdf.String,
    bytes,
    pikepdf.Array,
    pikepdf.Dictionary,
    "PdfInlineImage",
    None,
]
ContentStreamInstruction = Union[
    Tuple[List[NormalizedOperand], pikepdf.Operator], bytes
]


# pylint: disable=too-few-public-methods
class _Sentinel:
    """A sentinel that we should pass through an original binary stream fragment"""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"<{self.name}>"


ORIGINAL_BYTES = _Sentinel("ORIGINAL_BYTES")


@dataclass(frozen=True)
class StreamContext:
    """Context passed to handlers during stream processing.

    Attributes:
        pre_input (Dict[str, Any]): State snapshot *before* the current operator ran.
        post_input (Dict[str, Any]): State snapshot *after* the current operator ran.
        tracker (BaseStateTracker): Reference to the active state tracker instance.
        editor (StreamEditor): Reference to the parent editor instance.
    """

    pre_input: Optional[Dict[str, Any]]
    post_input: Optional[Dict[str, Any]]
    output: "TargetStateTracker"
    pdf: Optional[pikepdf.Pdf] = None
    page: Optional[pikepdf.Page] = None
    container: Optional[pikepdf.Object] = None
    tracker: Any = None


@runtime_checkable
class StreamHandler(Protocol):
    @property
    def modified_operators(self) -> Set[str]: ...

    def handle_operator(
        self,
        op: str,
        operands: List[NormalizedOperand],
        context: StreamContext,
        raw_bytes: bytes,
    ) -> List[Union[ContentStreamInstruction, bytes]]: ...


# --- Main Editor Class ---
class StreamEditor:
    """
    The main engine for parsing and modifying a PDF content stream.

    It iterates through a source stream (provided by ``pdfminer``), allows
    handlers to intercept operators, and constructs a new content stream.

    Args:
        source_iterator: Iterator yielding parsed PDF operators and state.
        handler: The logic registry.
        tracker: The state tracker.
        optimizer: Optional optimization function.
        page: The pikepdf Page being edited.
        container: The container object (Page or XObject).
        is_page_root: True if this is the main page content, False for XObjects.
    """

    def __init__(
        self,
        source_iterator,
        handler: StreamHandler,
        tracker: Any,
        optimizer: Optional[Callable[[List[Any]], List[Any]]] = None,
        page: Optional[pikepdf.Page] = None,
        pdf: Optional[pikepdf.Pdf] = None,
        container: Optional[pikepdf.Object] = None,
        is_page_root: bool = True,
    ):
        self.source_iter = source_iterator
        self.handler = handler
        self.tracker = tracker
        self.optimizer = optimizer
        self.page = page
        self.pdf = pdf
        self.container = container
        self.is_page_root = is_page_root

        self.last_input_pos = np.array([0.0, 0.0, 1.0])
        self._pending_ops: List[Union[ContentStreamInstruction, _Sentinel]] = []
        self._final_chunks: List[bytes] = []

        # --- Interception Logic (Step 6) ---
        # The editor intercepts operators if:
        # A) The Handler wants to modify them
        # B) The Optimizer needs them to be buffered (context)
        self.handler_ops = self.handler.modified_operators
        self.intercept_list = set(self.handler_ops)

        if self.optimizer and hasattr(self.optimizer, "relevant_operators"):
            self.intercept_list.update(self.optimizer.relevant_operators)

    def _normalize_instruction(self, item: Any):
        """
        Syntactic Sugar logic.
        Converts a flexible user return value into a standardized (operands, op) tuple.
        """
        # breakpoint()
        if isinstance(item, tuple):
            return self._normalize_instruction_tuple(item)
        if isinstance(item, bytes):
            # binary pass-through
            return item
        if isinstance(item, str):
            # implicit operator
            return ([], Operator(item))
        if isinstance(item, Operator):
            # actual operator
            return ([], item)
        if item == [ORIGINAL_BYTES]:  # fix a reasonable user error
            return ORIGINAL_BYTES
        raise ValueError(f"Could not normalize instruction: {item}")

    def _normalize_instruction_tuple(self, item: Any):
        if len(item) == 2:
            ops, operator = item
            if isinstance(operator, str):
                operator = Operator(operator)
            if not isinstance(ops, (list, tuple, Array)):
                ops = [ops]
            return (ops, operator)
        if len(item) == 1 and isinstance(item[0], str):
            return self._normalize_instruction(item[0])
        raise ValueError(f"Could not normalize intruction tuple: {item}")

    def __repr__(self):
        return (
            "StreamEditor(\n  "
            + ",\n  ".join(
                f"{x}={self.__getattribute__(x)}"
                for x in [
                    "source_iter",
                    "handler",
                    "tracker",
                    "optimizer",
                    "page",
                    "pdf",
                    "container",
                    "last_input_pos",
                    "_pending_ops",
                    "_final_chunks",
                    "handler_ops",
                    "intercept_list",
                    "optimizer",
                ]
            )
            + "\n)"
        )

    @property
    def current_position(self) -> np.ndarray:
        """Return current position"""
        return self.last_input_pos

    def process(self) -> bytes:
        """Executes the editing process and returns the new stream bytes."""
        self._final_chunks = []
        self._pending_ops = []
        pre_input_state = None

        self._call_special_handler("^", None)

        for step in self.source_iter:
            # breakpoint()
            pre_input_state = self._process_step(step, pre_input_state)

        self._call_special_handler("$", pre_input_state)

        self._flush_pending()
        ret = b"".join(self._final_chunks) + b"\n"
        return ret

    def _process_step(self, step, pre_input_state):

        op = step["operator"]
        operands = step["operands"]
        post_input_state = step["state"]
        raw_bytes = step.get("raw_bytes", b"")

        # 1. Update Tracker with PRE-input state from engine
        if pre_input_state:
            self.tracker.set_state(pre_input_state)

        # 2. Check optimization/interception safety
        if self._is_safe_to_optimize(op, operands, self.intercept_list):

            if op in self.handler_ops:
                # Case A: The Handler wants to modify this
                # breakpoint()
                self._call_handler(
                    op, operands, raw_bytes, pre_input_state, post_input_state
                )
            else:
                # Case B: Optimizer-only (Pass-through to buffer)
                # We must update the tracker immediately because the handler won't do it
                # and we aren't modifying the operands.

                # Buffer the parsed operator so the optimizer sees it
                self._pending_ops.append((operands, op))

        else:
            self._flush_pending()
            self._append_chunk(self._final_chunks, raw_bytes)

        # 3. Advance Input State Tracking
        pre_input_state = post_input_state
        if pre_input_state:
            self.last_input_pos = extract_text_position(pre_input_state)

        return pre_input_state

    def _call_special_handler(self, op, state):
        if op in self.handler_ops:
            self._call_handler(op, None, None, state, state)

    def _call_handler(self, op, operands, raw_bytes, pre_input_state, post_input_state):
        ctx = StreamContext(
            pre_input=pre_input_state,
            post_input=post_input_state,
            output=self.tracker,
            page=self.page,
            pdf=self.pdf,
            container=self.container,
            tracker=self.tracker,
        )
        self._buffer_modified_op(op, operands, ctx, raw_bytes)

    def _is_safe_to_optimize(
        self, op: str, operands: List[Any], intercept_list: Set[str]
    ) -> bool:
        if op not in intercept_list:
            return False
        if any(
            isinstance(arg, int)
            and (arg > 1152921504606846976 or arg < -1152921504606846976)
            for arg in operands
        ):
            return False
        if any(isinstance(arg, PDFStream) for arg in operands):
            return False
        return True

    def _buffer_modified_op(self, op, operands, context, raw_bytes):
        # Generic Handler Call
        new_ops_or_sentinels = self.handler.handle_operator(
            op, operands, context, raw_bytes
        )

        if new_ops_or_sentinels is None:
            return

        if not isinstance(new_ops_or_sentinels, list):
            new_ops_or_sentinels = [[new_ops_or_sentinels]]

        for item in new_ops_or_sentinels:
            if item is ORIGINAL_BYTES:
                self._pending_ops.append((operands, Operator(op)))
            else:
                normalized = self._normalize_instruction(item)
                # breakpoint()
                if isinstance(normalized, bytes):
                    # Direct binary injection
                    self._flush_pending()
                    self._append_chunk(self._final_chunks, normalized)
                elif normalized:
                    self._pending_ops.append(normalized)

    def _flush_pending(self):
        if self._pending_ops:
            if self.optimizer:
                optimizable = [
                    x
                    for x in self._pending_ops
                    if not isinstance(x, (bytes, _Sentinel))
                ]
                optimized = self.optimizer(optimizable)
            else:
                optimized = [
                    x
                    for x in self._pending_ops
                    if not isinstance(x, (bytes, _Sentinel))
                ]

            if optimized:
                chunk = pikepdf.unparse_content_stream(optimized)
                self._append_chunk(self._final_chunks, chunk)
            self._pending_ops.clear()

    def _append_chunk(self, chunks: List[bytes], chunk: bytes):
        if not chunk:
            return
        if chunks:
            last = chunks[-1]
            if not (last and last[-1] in b"\x00\t\n\x0c\r ") and not (
                chunk and chunk[0] in b"\x00\t\n\x0c\r "
            ):
                chunks.append(b"\n")
        chunks.append(chunk)

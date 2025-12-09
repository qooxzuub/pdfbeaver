# src/pdfbeaver/registry.py
"""
A user-friendly registry for stream handlers.

Implements the StreamHandler protocol (consumed by StreamEditor)
but allows function-based registration with flexible signatures.
"""

import inspect
import logging
from typing import Any, Callable, Dict, List, Set, Union

from .editor import (
    ORIGINAL_BYTES,
    ContentStreamInstruction,
    NormalizedOperand,
    StreamContext,
)

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """
    A user-friendly registry for stream handlers.
    Implements the StreamHandler protocol (consumed by StreamEditor)
    but allows function-based registration with flexible signatures.
    """

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        # Helper for users to return "do nothing" (pass-through)
        # pylint: disable=invalid-name
        self.PASS_THROUGH = [ORIGINAL_BYTES]

    @property
    def modified_operators(self) -> Set[str]:
        """Returns the set of operators registered for interception."""
        return set(self._handlers.keys())

    def register(self, *ops: str):
        """
        Decorator to register a function for specific operators.

        The decorated function can accept any combination of the following arguments
        (detected by name):

        * ``args`` or ``arguments`` or ``operands``: ``List[NormalizedOperand]``
        * ``context``: :class:`~pdfbeaver.editor.StreamContext`
        * ``raw_bytes``: ``bytes``
        * ``op`` or ``operator``: ``str``
        * ``pdf``: ``pikepdf.Pdf``
        * ``page``: ``pikepdf.Page``

        Example:
            .. code-block:: python

                @registry.register("Tj", "TJ")
                def my_handler(operands, context):
                    ...

        Args:
            *ops: One or more operator strings (e.g., "Tj", "Do", "re") to intercept.
        """

        def decorator(func: Callable):
            sig = inspect.signature(func)
            params = set(sig.parameters)
            allowed_params = {
                "args",
                "arguments",
                "container",
                "context",
                "op",
                "operands",
                "operator",
                "page",
                "pdf",
                "raw_bytes",
            }

            if bad_param := any((x not in allowed_params for x in params)):
                raise ValueError(
                    f"Parameter name {bad_param} not allowed. "
                    f"Allowed parameter names are: {allowed_params}"
                )

            def wrapper(operands, context, raw_bytes, op_name):
                kwargs_all = {
                    "args": operands,
                    "arguments": operands,
                    "container": context.container if context else None,
                    "context": context,
                    "op": op_name,
                    "operands": operands,
                    "operator": op_name,
                    "page": context.page if context else None,
                    "pdf": context.pdf if context else None,
                    "raw_bytes": raw_bytes,
                }
                kwargs = {k: kwargs_all[k] for k in params}

                result = func(**kwargs)
                return self._normalize_return_value(result)

            for op in ops:
                self._handlers[op] = wrapper
            return func

        return decorator

    def _normalize_return_value(self, result: Any) -> List[Any]:
        """
        Ensures the handler return value is always a list of instructions.
        Allows users to return single items (str, bytes, tuple) without wrapping in [].
        """
        if result is None:
            return []

        # If it's a list (and not a string/bytes), assume it's a list of instructions
        if isinstance(result, list):
            return result

        # Handle generators
        if isinstance(result, (map, filter)) or inspect.isgenerator(result):
            return list(result)

        # If it's a single item (str, bytes, tuple, Sentinel), wrap it
        return [result]

    def handle_operator(
        self,
        op: str,
        operands: List[NormalizedOperand],
        context: StreamContext,
        raw_bytes: bytes,
    ) -> List[Union[ContentStreamInstruction, bytes]]:
        """
        Standard entry point called by StreamEditor.
        """
        handler = self._handlers.get(op)
        if not handler:
            return [raw_bytes]

        return handler(operands, context, raw_bytes, op)


default_registry = HandlerRegistry()

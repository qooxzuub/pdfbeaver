# src/pdfbeaver/.state_iterator.py
#!/usr/bin/env python3
#
# This file includes code adapted from pdfminer.six (https://github.com/pdfminer/pdfminer.six)
# Copyright (c) 2004-2016 Yusuke Shinyama <yusuke at cs dot nyu dot edu>
#
# Licensed under the MIT License.
# You may obtain a copy of the License at: https://opensource.org/licenses/MIT
# ------------------------------------------------------------------------------

"""Module: pdfbeaver.state_iterator

This module provides a `StreamStateIterator` class that is a
customized PDF content stream parser and iterator.
"""

import logging
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
from pdfminer.pdfdevice import PDFDevice
from pdfminer.pdfinterp import PDFContentParser, PDFPageInterpreter, PDFResourceManager
from pdfminer.pdftypes import PDFStream
from pdfminer.psparser import PSEOF, PSKeyword

from .utils.pdf_conversion import normalize_pdf_operand

# Configure logger for this module
logger = logging.getLogger(__name__)


class StreamStateIterator(PDFPageInterpreter):
    """Iterates over a content stream, yielding detailed state steps.

    Inherits from ``pdfminer.PDFPageInterpreter``. Instead of just executing
    commands, it yields a dictionary for every operator containing:

    * ``op``: The operator name (str)
    * ``operands``: List of operands
    * ``state_after``: A snapshot of the graphics/text state *after* execution.
    * ``raw``: The raw bytes corresponding to this instruction.

    Just like its parent class, you must call the method
    ``init_resources(self, resource: Dict[object, object])``` in order
    to initialize resources.

    """

    def __init__(self, rsrcmgr: PDFResourceManager, device: PDFDevice):
        super().__init__(rsrcmgr, device)
        self.init_state(ctm=(1, 0, 0, 1, 0, 0))
        super().init_resources({})

    def capture_state(self) -> Dict[str, Any]:
        """Captures and returns a snapshot of current graphics and text state."""
        tstate = self.textstate.copy()

        tstate.matrix = list(tstate.matrix)
        tstate.linematrix = list(tstate.linematrix)

        gstate = self.graphicstate.copy()

        font_name: Optional[str] = None
        if tstate.font:
            font_name = getattr(tstate.font, "basefont", None)

        return {
            "ctm": self.ctm,
            "tstate": tstate,
            "gstate": gstate,
            "font_name": font_name,
            "font_obj": tstate.font,
        }

    def _get_parser_pos(self, parser: PDFContentParser) -> int:
        """
        Calculates the exact byte offset of the parser head.
        """
        # 1. Determine buffer index
        buffer_index = parser.charpos

        # 2. Check for buffer
        if not hasattr(parser, "buf"):
            return 0

        # 3. Calculate absolute position
        if parser.fp:
            # parser.fp.tell() is the file position at the END of the current buffer chunk.
            pos = parser.fp.tell() - len(parser.buf) + buffer_index
            return max(0, pos)

        # If no file pointer (memory stream), the buffer likely holds the stream
        return buffer_index

    def _consolidate_streams(self, streams: Sequence[object]) -> bytes:
        """Consolidates multiple stream objects into a single bytes object."""
        combined_data = bytearray()
        for s in streams:
            seen_ids = set()
            while hasattr(s, "resolve"):
                if id(s) in seen_ids:
                    # loop
                    break
                seen_ids.add(id(s))
                s = s.resolve()
            if hasattr(s, "get_data"):
                data = s.get_data()
            elif hasattr(s, "get_rawdata"):
                data = s.get_rawdata()
            elif hasattr(s, "read_bytes"):
                data = s.read_bytes()
            elif isinstance(s, bytes):
                data = s
            else:
                data = str(s).encode("latin1")

            combined_data.extend(data)
            if not data[-1:].isspace():
                combined_data.extend(b" ")

        return bytes(combined_data.strip())

    def _process_operator(
        self,
        op_name: str,
        proc_stack: List[Any],
        parser: PDFContentParser,
        final_bytes: bytes,
        cmd_start_pos: int,
    ) -> Tuple[Dict[str, Any], int]:
        # pylint: disable=too-many-arguments, too-many-positional-arguments
        """Executes operator logic, captures state, and extracts raw bytes."""

        # if op_name in ('Tj', 'TJ'):
        # 1. Execute Internal Logic (State Tracking)
        func_name = f"do_{op_name}"
        if hasattr(self, func_name):
            func = getattr(self, func_name)
            try:
                func(*proc_stack)
            except TypeError as e:
                logger.debug("Internal processing failed for %s: %s", op_name, e)

        # 2. Capture State
        current_state = self.capture_state()

        # 3. Extract Raw Bytes for Pass-Through
        cmd_end_pos = self._get_parser_pos(parser)

        if cmd_end_pos < cmd_start_pos:
            # pdfminer seems to set position to 0 on EOF
            # so we just consume everything remaining
            cmd_end_pos = len(final_bytes)

        # Check range validity
        if cmd_end_pos >= cmd_start_pos >= 0:
            raw_bytes = final_bytes[cmd_start_pos:cmd_end_pos]
        else:
            raw_bytes = b""

        # 4. Normalize
        clean_operands = list(map(normalize_pdf_operand, proc_stack))

        result = {
            "operator": op_name,
            "operands": clean_operands,
            "state": current_state,  # copy.deepcopy(current_state),
            "raw_bytes": raw_bytes,
        }
        return result, cmd_end_pos

    def execute(
        self, streams: Sequence[object]
    ) -> Iterator[Dict[str, Any]]:  # type:ignore
        """
        Parses the streams and yields step dictionaries.
        """
        # 1. Consolidate streams into a single bytes buffer.
        final_bytes = self._consolidate_streams(streams)

        if not final_bytes:
            return

        # 2. Wrap in PDFStream for the parser
        single_stream_obj = PDFStream({}, final_bytes)

        # 3. Instantiate PDFContentParser
        parser = PDFContentParser([single_stream_obj])

        proc_stack: List[Any] = []
        cmd_start_pos = 0

        while True:
            # Calculate start position BEFORE consuming the token.
            current_pos = self._get_parser_pos(parser)

            if not proc_stack:
                cmd_start_pos = current_pos

            try:
                # Handle tuple return (pos, token) from nextobject()
                result = parser.nextobject()

                if isinstance(result, tuple):
                    _, obj = result
                else:
                    obj = result
            except PSEOF:
                break

            # Case 1: It is an Operator (Keyword)
            if isinstance(obj, PSKeyword):
                op_name = obj.name.decode("ascii")
                step_data, cmd_end_pos = self._process_operator(
                    op_name, proc_stack, parser, final_bytes, cmd_start_pos
                )
                # print(
                #     f"Yielding: {op_name}{proc_stack} {step_data['state']['tstate'].matrix}"
                # )
                yield step_data

                proc_stack = []
                cmd_start_pos = cmd_end_pos

            # Case 2: Operand
            else:
                proc_stack.append(obj)

    # pdfminer conventions:
    # text matrices (3x3 matrices, in pdf spec section 9.4.2)
    # vs
    # pdfminer textstate properties: matrix (a 6-tuple) and linematrix (a 2-tuple).
    #
    # textstate properties are not clearly documented AFAIK.
    # And the math in the reference implementations of the text operators
    # don't seem to match the PDF spec.
    #
    # But the idea might be:
    #
    # textstate.matrix = tuple(T_{m}[:,:2]) (simply T_{m} as a 6-tuple)
    # textstate.linematrix = tuple( (ts.textmatrix - T_{lm})[2,0:1] )
    #
    # The idea is that (x,y) = textstate.linematrix
    # records the difference between T_{m} and T_{lm}:
    #
    # T_{lm} = T_m - [0 0 0;0 0 0; x y 0]

    def do_Td(self, tx, ty) -> None:
        """
        Move to the start of the next line, offset from the start of the
        current line by (tx, ty). tx and ty shall denote numbers
        expressed in unscaled text space units.

        Math: T_{m} = T_{lm} = (I+Delta) @ T_{lm}
        where Delta = [0,0,0;0,0,0;tx,ty,0]

        """
        # print(f"Before do_Td: {self.textstate}")
        a, b, c, d, e, f = self.textstate.matrix

        textmatrix_np = np.array([[a, b, 0], [c, d, 0], [e, f, 1]])
        g, h = self.textstate.linematrix
        linematrix_np = textmatrix_np + np.array([[0, 0, 0], [0, 0, 0], [g, h, 0]])

        tm = np.array([[1, 0, 0], [0, 1, 0], [tx, ty, 1]]) @ linematrix_np
        self.textstate.matrix = tuple(map(float, tm[:, :2].flatten()))

        # T_{lm} = T_m, so ts.linematrix = (0, 0)
        self.textstate.linematrix = (0, 0)
        # print(f"At end of do_Td: {self.textstate}")

    def do_TD(self, tx, ty):
        """Move to the start of the next line, offset from the start of the
        current line by (tx, ty). As a side effect, this operator shall set
        the leading parameter in the text state.

        So tx ty TD is same as -ty TL tx ty Td"""
        super().do_TL(-ty)
        self.do_Td(tx, ty)

    def do_TJ(self, seq: List[Any]) -> None:
        """Updates the text matrix based on string width, kerning, and spacing.
        Formula: tx = [ (w0 * fontsize) + Tc + (space? Tw) ] * (scaling/100)

        This should affect T_{m} only. T_{lm} should not be changed.
        But this means we have to compensate by updating
        textstate.linematrix because is represents the difference
        between T_{m} and T_{lm}. See math comment in
        state_iterator.py.

        Note that do_Tj uses this so does not (hopefully) need a separate implementation?
        Or is it calling the parent implementation?? FIXME CHECK

        """
        ts = self.textstate
        if ts.font is None:
            return
        h_scale = ts.scaling / 100.0
        tx_accum = 0.0

        for item in seq:
            if isinstance(item, (int, float)):
                # Kerning: -num / 1000 * fontsize * h_scale
                tx_accum -= (item / 1000.0) * ts.fontsize * h_scale
            elif isinstance(item, (bytes, str)):
                # 1. Glyph Widths (scaled by font size)
                w_glyphs = ts.font.string_width(item) * ts.fontsize

                # 2. Character Spacing (Tc)
                # Heuristic: 1 byte = 1 char (correct for Type1/TrueType, approx for CID)
                w_char_spacing = len(item) * ts.charspace

                # 3. Word Spacing (Tw) applied to ASCII spaces (32)
                # Only applies if font is not strictly symbolic/multibyte?
                # PDF Spec is complex, but checking for byte 32 is the standard heuristic.
                w_word_spacing = (
                    item.count(b" " if isinstance(item, bytes) else " ") * ts.wordspace
                )

                # Sum and apply Horizontal Scaling
                tx_accum += (w_glyphs + w_char_spacing + w_word_spacing) * h_scale

        self._set_matrices_for_kerning_block(ts, tx_accum)

    def _set_matrices_for_kerning_block(self, ts, tx_accum):
        # Apply Translation to Text Matrix
        # Tm = [a b 0 c d 0 e f 1]
        # We advance along the 'a' and 'b' vectors of the text line
        a, b, c, d, e, f = ts.matrix
        # Move e, f by the calculated x-displacement projected onto a, b
        ts.matrix = (a, b, c, d, e + tx_accum * a, f + tx_accum * b)

        # We want to keep T_{lm} unchanged!!
        # This is what the math gives. Unless I made a mistake...
        g, h = ts.linematrix
        ts.linematrix = (g - tx_accum * a, h - tx_accum * b)

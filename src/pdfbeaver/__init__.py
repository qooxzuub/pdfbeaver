# src/pdfbeaver/__init__.py
"""
pdf-stream-editor: A generic library for modifying PDF content streams.

This library bridges the gap between `pikepdf` (which is excellent for structural
PDF editing but treats content streams as opaque blobs) and `pdfminer` (which
is excellent for parsing content but cannot write it back).

It provides a stream-based editing model where users can register callbacks
for specific PDF operators (like ``Tj`` for text or ``re`` for rectangles).
"""
import logging

from .api import ProcessingOptions, modify_page, process
from .base_state_tracker import BaseStateTracker
from .editor import ORIGINAL_BYTES, NormalizedOperand, StreamContext
from .literate_state_tracker import LiterateStateTracker
from .registry import HandlerRegistry, default_registry
from .utils.pdf_conversion import normalize_pdf_operand
from .utils.pdf_geometry import extract_text_position

# the easy decorator alias
register = default_registry.register

UNCHANGED = [ORIGINAL_BYTES]


# pylint: disable=too-few-public-methods
class SuppressFontBBoxWarning(logging.Filter):
    """Suppress a warning from pdfminer"""

    def filter(self, record):
        # Return False to suppress the log, True to allow it
        return (
            "get FontBBox from font descriptor because None cannot be parsed"
            not in record.getMessage()
        )


# Attach filter to the specific logger used by pdfminer.pdffont
logging.getLogger("pdfminer.pdffont").addFilter(SuppressFontBBoxWarning())


__all__ = [
    "process",
    "modify_page",
    "register",
    "ProcessingOptions",
    "HandlerRegistry",
    "StreamContext",
    "NormalizedOperand",
    "BaseStateTracker",
    "LiterateStateTracker",
    "extract_text_position",
    "normalize_pdf_operand",
    "UNCHANGED",
    "ORIGINAL_BYTES",
]

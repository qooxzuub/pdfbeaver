# src/pdfbeaver/literate_state_tracker.py
"""A PDF content stream state tracker which understands fonts"""
import logging
from typing import Any, Dict

import numpy as np

from .base_state_tracker import BaseStateTracker
from .utils.pdf_conversion import miner_matrix_to_np

logger = logging.getLogger(__name__)


class LiterateStateTracker(BaseStateTracker):
    """
    Font-aware state tracker.

    Inherits generic math from :class:`BaseStateTracker`.
    Adds capability to calculate visual text position (cursor flow) by resolving
    font metrics via ``pdfminer``.

    Args:
        target_font_cache: A dictionary mapping font names to pdfminer Font objects.
        custom_encoding_maps: A dictionary for custom CMap encodings.
    """

    def __init__(
        self, target_font_cache: Dict[str, Any], custom_encoding_maps: Dict[str, Any]
    ):
        super().__init__()
        self.target_font_cache = target_font_cache
        self.custom_encoding_maps = custom_encoding_maps

        self.active_wrapper = None
        self.active_encoding = None

    def set_active_proxy(self, font_wrapper, encoding_map):
        """
        Registers the active font metrics for width calculation.
        Typically called by a Handler when it processes 'Tf'.
        """
        self.active_wrapper = font_wrapper
        self.active_encoding = encoding_map

    def get_current_user_pos(self) -> np.ndarray:
        """
        Returns the (x, y) position of the cursor in User Space.

        Calculated as: Origin(0,0) x Tm x CTM.

        Returns:
            np.ndarray: A 3-element vector [x, y, 1] representing the cursor position.
        """
        # Start of text space (0, 0)
        p = np.array([0.0, 0.0, 1.0])

        # Apply Text Matrix
        a, b, c, d, e, f = self.textstate.matrix
        tm = np.array([[a, b, 0], [c, d, 0], [e, f, 1]])

        # Apply CTM
        ctm = miner_matrix_to_np(self.gstate.ctm)

        return p @ tm @ ctm

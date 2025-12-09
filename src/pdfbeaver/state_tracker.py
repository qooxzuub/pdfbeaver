# src/pdfbeaver/state_tracker.py
"""Tracks the PDF Text State parameters as defined in the PDF 1.7 Reference.

Attributes:
    char_spacing (float): Character spacing ($Tc$). Defaults to 0.0.
    word_spacing (float): Word spacing ($Tw$). Defaults to 0.0.
    horiz_scaling (float): Horizontal scaling ($Tz$). Defaults to 100.0.
    leading (float): Text leading ($Tl$). Defaults to 0.0.
    font_name (Optional[str]): The resource name of the current font (e.g. '/F1'),
        if available.
    fontsize (float): The current font size ($Tfs$).
    render_mode (int): The text rendering mode ($Tr$).
    rise (float): Text rise ($Ts$). Defaults to 0.0.
    knockout (bool): Text knockout flag. Defaults to True.
    matrix (List[float]): The Text Matrix ($Tm$), stored as a 6-element list
        ``[a, b, c, d, e, f]``.
    line_matrix (List[float]): The Text Line Matrix ($Tlm$), stored as a
        6-element list.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .utils.pdf_conversion import miner_matrix_to_np

logger = logging.getLogger(__name__)


@dataclass
class TextState:  # pylint: disable=too-many-instance-attributes
    """Tracks the PDF Text State parameters.

    Attributes:
        char_spacing (float): Character spacing ($Tc$). Defaults to 0.0.
        word_spacing (float): Word spacing ($Tw$). Defaults to 0.0.
        horiz_scaling (float): Horizontal scaling ($Tz$). Defaults to 100.0.
        leading (float): Text leading ($Tl$). Defaults to 0.0.
        font_name (Optional[str]): The PostScript name of the current font
            (e.g., 'Helvetica-Bold'), if available. Note: This is *not* the
            Resource Name (e.g., '/F1').
        fontsize (float): The current font size ($Tfs$).
        render_mode (int): The text rendering mode ($Tr$).
        rise (float): Text rise ($Ts$). Defaults to 0.0.
        knockout (bool): Text knockout flag. Defaults to True.
        matrix (List[float]): The Text Matrix ($Tm$), stored as a 6-element list
            ``[a, b, c, d, e, f]``.
        line_matrix (List[float]): The Text Line Matrix ($Tlm$), stored as a
            6-element list.
    """

    char_spacing: float = 0.0
    word_spacing: float = 0.0
    horiz_scaling: float = 100.0
    leading: float = 0.0
    font_name: Optional[str] = None
    fontsize: float = 0.0
    render_mode: int = 0
    rise: float = 0.0
    knockout: bool = True

    # Matrices are stored as list of 6 floats [a, b, c, d, e, f]
    matrix: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    line_matrix: List[float] = field(
        default_factory=lambda: [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    )

    def copy(self):
        """Return a copy of this state"""
        new_obj = TextState(**self.__dict__)
        new_obj.matrix = list(self.matrix)
        new_obj.line_matrix = list(self.line_matrix)
        return new_obj


@dataclass
class GraphicsState:
    """Tracks the PDF Graphics State parameters.

    Attributes:
        ctm (List[float]): The Current Transformation Matrix ($CTM$), stored as
            a 6-element list ``[a, b, c, d, e, f]``.
    """

    ctm: np.ndarray = field(default_factory=lambda: [1.0, 0.0, 0.0, 1.0, 0.0, 0.0])

    def copy(self):
        """Return a copy of this state"""
        new_obj = GraphicsState(**self.__dict__)
        new_obj.ctm = list(self.ctm)
        return new_obj


class StateTracker:
    """
    State tracker. Tracks the CTM (Graphics) and Text Matrices.

    This tracker acts as a bridge between the underlying ``pdfminer`` state machine
    and the ``pdfbeaver`` context. It ingests snapshots of the state provided by the
    iterator and makes them accessible in a clean, pythonic format.

    """

    def __init__(self):
        self.gstate = GraphicsState()
        self.gstack: List[GraphicsState] = []
        self.textstate = TextState()
        self.text_obj_active = False

    def get_matrices(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculates the effective transformation matrices.

        Returns:
            Tuple[np.ndarray, np.ndarray]: A tuple containing:
                1. The CTM (3x3 numpy array).
                2. The Text Render Matrix (CTM x TM) (3x3 numpy array).
        """
        ctm = miner_matrix_to_np(self.gstate.ctm)
        tm = miner_matrix_to_np(self.textstate.matrix)
        trm = tm @ ctm
        return ctm, trm

    def set_state(self, state: Dict[str, Any]):
        """
        Updates the internal state to match the snapshot provided by the iterator.
        This is the 'Passive Tracking' model: we trust the engine (pdfminer).
        """
        if not state:
            return

        # Sync CTM (pdfminer provides tuple/list of 6 floats)
        if "ctm" in state:
            self.gstate.ctm = list(state["ctm"])

        # Sync Text State
        # Note: pdfminer returns a PDFTextState object in 'tstate'
        # We map specific fields we care about to our internal structure
        if "tstate" in state:
            src = state["tstate"]
            dst = self.textstate

            dst.char_spacing = src.charspace
            dst.word_spacing = src.wordspace
            dst.horiz_scaling = src.scaling
            dst.leading = src.leading
            dst.font_name = getattr(src.font, "basefont", None) if src.font else None
            dst.fontsize = src.fontsize
            dst.render_mode = src.render
            dst.rise = src.rise
            dst.matrix = src.matrix
            dst.line_matrix = src.linematrix

    def get_snapshot(self) -> Dict[str, Any]:
        """Returns a snapshot of the current state."""
        return {
            "ctm": self.gstate.ctm,
            "tstate": self.textstate.copy(),
            "gstate": self.gstate.copy(),
            "font_name": self.textstate.font_name,
        }

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

# src/pdfbeaver/utils/pdf_geometry.py
"""
Geometry utilities for calculating cursor positions and transformations from PDF state.
"""
from typing import Any, Dict

import numpy as np


def extract_text_position(state: Dict[str, Any]) -> np.ndarray:
    """
    Calculates the absolute (x, y, 1) position from the graphics state.
    Requires 'tstate' (Text State) and 'ctm' (Current Transformation Matrix).
    Handles both List-based CTM (pdfminer) and Numpy-based CTM.
    """
    if not state or "tstate" not in state or "ctm" not in state:
        # Return origin if state is missing
        return np.array([0.0, 0.0, 1.0])

    # Text Matrix (Tm) is typically a list/object with a .matrix attribute
    # [a, b, c, d, e, f]
    tstate = state["tstate"]
    if hasattr(tstate, "matrix"):
        tm = tstate.matrix
    elif isinstance(tstate, dict) and "matrix" in tstate:
        tm = tstate["matrix"]
    else:
        tm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]

    # Translation components (e, f) are at indices 4, 5
    tx, ty = float(tm[4]), float(tm[5])

    ctm = state["ctm"]

    # CASE A: CTM is a NumPy Array (3x3)
    # Used by StateTracker
    if isinstance(ctm, np.ndarray) and ctm.shape == (3, 3):
        # Point vector [x, y, 1]
        local_point = np.array([tx, ty, 1.0])
        # Apply transformation: P_new = P_old @ Matrix
        return local_point @ ctm

    # CASE B: CTM is a List of 6 floats
    # Used by pdfminer / StreamStateIterator
    # CTM = [a, b, c, d, e, f]
    try:
        # x' = x*a + y*c + e
        # y' = x*b + y*d + f
        # tx corresponds to x, ty corresponds to y (in text space origin)
        ux = tx * ctm[0] + ty * ctm[2] + ctm[4]
        uy = tx * ctm[1] + ty * ctm[3] + ctm[5]
        return np.array([ux, uy, 1.0])
    except (IndexError, TypeError):
        # Fallback for malformed state
        return np.array([tx, ty, 1.0])

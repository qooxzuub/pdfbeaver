import numpy as np

from pdfbeaver.utils.pdf_geometry import extract_text_position

# --- pdf_geometry.py Coverage ---


def test_geometry_numpy_ctm():
    """Test lines 32-38: CTM is a NumPy array."""
    # This path is used when the StateTracker (which stores np arrays)
    # calls this util, vs the Iterator (which stores lists).

    # Setup: Simple translation matrix (10, 20)
    ctm = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [10.0, 20.0, 1.0]])

    # tstate with identity matrix
    tstate = type("MockTState", (), {"matrix": [1, 0, 0, 1, 0, 0]})()

    state = {"tstate": tstate, "ctm": ctm}

    pos = extract_text_position(state)
    # Origin (0,0) -> translated by (10,20) -> (10, 20)
    assert np.allclose(pos, [10.0, 20.0, 1.0])


def test_geometry_tstate_variations():
    """Test lines 22-25: tstate as dict or missing matrix."""

    ctm = [1, 0, 0, 1, 0, 0]

    # 1. tstate is a dict (Line 22)
    # (Rare, but supported for raw data processing)
    state_dict = {"tstate": {"matrix": [1, 0, 0, 1, 50, 50]}, "ctm": ctm}
    pos = extract_text_position(state_dict)
    assert pos[0] == 50.0

    # 2. tstate is missing matrix (Line 24)
    state_empty = {"tstate": {}, "ctm": ctm}
    pos = extract_text_position(state_empty)
    # Should default to origin
    assert pos[0] == 0.0


def test_geometry_malformed_ctm():
    """Test lines 50-52: Exception handling for bad CTM."""
    tstate = type("MockTState", (), {"matrix": [1, 0, 0, 1, 100, 100]})()

    # CTM is "bad" (not a list of 6 floats)
    # This triggers the IndexError/TypeError in the calculation block
    state = {"tstate": tstate, "ctm": ["not", "enough", "items"]}

    # Should catch exception and return the local point (100, 100) without CTM applied
    pos = extract_text_position(state)
    assert pos[0] == 100.0
    assert pos[1] == 100.0

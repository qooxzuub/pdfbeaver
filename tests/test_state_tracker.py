import numpy as np

from pdfbeaver.state_tracker import StateTracker


def test_get_current_user_pos():
    tracker = StateTracker()

    # Set a known state
    # Text Matrix (Tm): Translate by (100, 200)
    tracker.textstate.matrix = [1.0, 0.0, 0.0, 1.0, 100.0, 200.0]

    # CTM: Scale by 2x (so 1 unit in user space = 2 units in device space, conceptually)
    # But CTM transforms user space to device space.
    # Wait, the calculation is p @ tm @ ctm.
    # Let's use an identity CTM for simplicity first, or a simple translation.
    tracker.gstate.ctm = [1.0, 0.0, 0.0, 1.0, 50.0, 50.0]

    # Expected Calculation:
    # Origin (0,0,1)
    # After Tm: (100, 200, 1)
    # After CTM (translate 50,50): (150, 250, 1)

    pos = tracker.get_current_user_pos()

    assert np.allclose(pos, [150.0, 250.0, 1.0])


def test_get_current_user_pos_with_rotation():
    tracker = StateTracker()

    # Text Matrix: Rotate 90 degrees and translate (100, 100)
    # Rotation 90 deg: cos=0, sin=1 => [0, 1, -1, 0, 0, 0]
    tracker.textstate.matrix = [0.0, 1.0, -1.0, 0.0, 100.0, 100.0]

    # CTM: Identity
    tracker.gstate.ctm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]

    # Expected: (0,0) -> rotated (0,0) -> translated (100, 100) -> (100, 100)
    # Let's verify a point offset.
    # Ideally get_current_user_pos just returns the origin of the current text line.

    pos = tracker.get_current_user_pos()
    assert np.allclose(pos, [100.0, 100.0, 1.0])

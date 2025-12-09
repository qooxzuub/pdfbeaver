# tests/test_core_mechanics.py
import numpy as np
import pytest
from pikepdf import String

from pdfbeaver.base_state_tracker import BaseStateTracker
from pdfbeaver.editor import StreamEditor
from pdfbeaver.registry import HandlerRegistry


def string_in_pdf_bytes(target_str: str, content_stream: bytes) -> bool:
    """
    Checks if a string is present in a PDF content stream, handling
    both Literal format '(Text)' and Hexadecimal format '<54657874>'.
    """
    text_bytes = target_str.encode("latin1")
    literal = b"(" + text_bytes + b")"
    hex_version = b"<" + text_bytes.hex().encode("ascii") + b">"
    return (literal in content_stream) or (hex_version in content_stream)


@pytest.fixture
def clean_registry():
    """A registry with simple, predictable logic."""
    reg = HandlerRegistry()

    @reg.register("Tj")
    def handle_text(operands, context):
        return [("Redacted", "Tj")]

    return reg


def test_passthrough_unregistered_ops(clean_registry):
    """Verify that ops NOT in the registry are passed through unchanged."""
    # MOCK DATA: Updated to match the dict keys yielded by StreamStateIterator
    source = [{"operator": "q", "operands": [], "raw_bytes": b"q", "state": {}}]

    editor = StreamEditor(iter(source), clean_registry, BaseStateTracker())
    result = editor.process()

    assert result.strip() == b"q"


def test_interception_and_modification(clean_registry):
    """Verify the editor intercepts 'Tj' and writes the handler's output."""
    # MOCK DATA
    source = [
        {"operator": "BT", "operands": [], "raw_bytes": b"BT", "state": {}},
        {
            "operator": "Tj",
            "operands": ["Secret"],
            "raw_bytes": b"(Secret) Tj",
            "state": {},
        },
        {"operator": "ET", "operands": [], "raw_bytes": b"ET", "state": {}},
    ]

    editor = StreamEditor(iter(source), clean_registry, BaseStateTracker())
    result = editor.process()

    # Check that 'Secret' is gone and 'Redacted' is there
    assert not string_in_pdf_bytes("Secret", result)
    assert string_in_pdf_bytes("Redacted", result)

    # Check that context ops remained
    assert b"BT" in result
    assert b"ET" in result


def test_state_tracking_mechanics():
    """
    Verify the tracker correctly calculates matrices from state snapshots.

    Since the tracker is now 'passive' (it receives state from pdfminer rather than
    calculating it from operators), we test that it correctly ingests data
    and computes the Text Render Matrix (TRM).
    """
    tracker = BaseStateTracker()

    # 1. Simulate an incoming state snapshot (as if pdfminer processed 'cm')
    # CTM = Translate(50, 50) -> [1, 0, 0, 1, 50, 50]
    fake_state_from_miner = {
        "ctm": [1.0, 0.0, 0.0, 1.0, 50.0, 50.0],
        # Text matrix is identity by default
        "tstate": type(
            "MockTState",
            (),
            {
                "charspace": 0,
                "wordspace": 0,
                "scaling": 100,
                "leading": 0,
                "render": 0,
                "rise": 0,
                "font": None,
                "fontsize": 12,
                "linematrix": [0] * 6,
                "matrix": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            },
        )(),
    }

    # 2. Update Tracker
    tracker.set_state(fake_state_from_miner)

    # 3. Check Math (CTM)
    # Note: Our tracker converts list -> numpy for calculation
    ctm, trm = tracker.get_matrices()

    assert isinstance(ctm, np.ndarray)
    assert ctm[2, 0] == 50.0  # x translation
    assert ctm[2, 1] == 50.0  # y translation

    # 4. Check TRM (Text Render Matrix)
    # TRM = Tm x CTM
    # Identity x Translate(50,50) = Translate(50,50)
    assert trm[2, 0] == 50.0
    assert trm[2, 1] == 50.0

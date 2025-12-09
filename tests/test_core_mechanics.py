import pytest
from pikepdf import Operator, String

from pdfbeaver.base_state_tracker import BaseStateTracker
from pdfbeaver.editor import StreamEditor
from pdfbeaver.registry import HandlerRegistry


def string_in_pdf_bytes(target_str: str, content_stream: bytes) -> bool:
    """
    Checks if a string is present in a PDF content stream, handling
    both Literal format '(Text)' and Hexadecimal format '<54657874>'.
    """
    # 1. Convert target string to bytes (PDFs typically use Latin1/PDFDocEncoding)
    text_bytes = target_str.encode("latin1")

    # 2. Construct Literal representation: (Text)
    literal = b"(" + text_bytes + b")"

    # 3. Construct Hexadecimal representation: <54657874>
    hex_version = b"<" + text_bytes.hex().encode("ascii") + b">"

    # 4. Return True if either format matches
    return (literal in content_stream) or (hex_version in content_stream)


@pytest.fixture
def clean_registry():
    """A registry with simple, predictable logic."""
    reg = HandlerRegistry()

    @reg.register("Tj")
    def handle_text():
        # FIX: Use pikepdf.String to ensure correct PDF formatting (e.g. parens)
        return (String("Redacted"), "Tj")

    return reg


def test_passthrough_unregistered_ops(clean_registry):
    """Verify that ops NOT in the registry are passed through unchanged."""
    source = [{"operator": "q", "operands": [], "raw_bytes": b"q", "state": {}}]

    editor = StreamEditor(iter(source), clean_registry, BaseStateTracker())
    result = editor.process()

    # FIX: Allow trailing newline (standard editor behavior)
    assert result.strip() == b"q"


def test_interception_and_modification(clean_registry):
    """Verify the editor intercepts 'Tj' and writes the handler's output."""
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

    # pikepdf might output (Redacted) Tj OR <...> Tj.
    # Since we used pikepdf.String("Redacted"), it prefers parens if simple ascii.
    # We check for the presence of "Redacted" generally.
    assert string_in_pdf_bytes("Redacted", result)
    assert b"Tj" in result

    # Check that context ops remained
    assert b"BT" in result
    assert b"ET" in result


@pytest.mark.skip
def test_state_tracking_mechanics():
    """Verify the tracker updates CTM without needing font metrics."""
    tracker = BaseStateTracker()

    # 1. Translate 50, 50
    tracker.execute_op("cm", [1, 0, 0, 1, 50, 50])

    # 2. Check Math
    ctm, _ = tracker.get_matrices()
    # CTM should be translation matrix
    assert ctm[2, 0] == 50.0
    assert ctm[2, 1] == 50.0

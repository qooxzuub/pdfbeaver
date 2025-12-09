import pytest
from pdfminer.pdftypes import PDFStream
from pikepdf import Operator

# We need to access private methods to test normalization directly
from pdfbeaver.editor import ORIGINAL_BYTES, StreamEditor, _Sentinel


# Mock objects to instantiate Editor
class MockHandler:
    modified_operators = set()

    def handle_operator(self, *args):
        return []


@pytest.fixture
def editor():
    """Returns an instantiated StreamEditor with dummy dependencies."""
    return StreamEditor(source_iterator=[], handler=MockHandler(), tracker=None)


def test_normalize_instruction_sugar(editor):
    """Test syntactic sugar in _normalize_instruction (Lines 163-181)."""

    # 1. String -> Operator (Line 174-176)
    res = editor._normalize_instruction("q")
    assert res == ([], Operator("q"))

    # 2. Operator -> Operator (Line 177-178)
    op = Operator("Q")
    res = editor._normalize_instruction(op)
    assert res == ([], op)

    # 3. List of Sentinel (Line 179-180)
    # This handles the case where a user returns [ORIGINAL_BYTES] instead of just ORIGINAL_BYTES
    res = editor._normalize_instruction([ORIGINAL_BYTES])
    assert isinstance(res, _Sentinel)

    # 4. Invalid Input (Line 181)
    with pytest.raises(ValueError, match="Could not normalize"):
        editor._normalize_instruction(123)  # Integers are not valid instructions


def test_normalize_instruction_tuple_errors(editor):
    """Test error handling in _normalize_instruction_tuple (Line 193)."""
    # Valid tuple is (operands, op) -> len 2
    # Invalid tuple: len 3
    with pytest.raises(ValueError, match="Could not normalize"):
        editor._normalize_instruction((1, 2, 3))


def test_repr(editor):
    """Test __repr__ (Lines 195-217)."""
    # Just ensure it doesn't crash and returns a string
    s = repr(editor)
    assert s.startswith("StreamEditor(")
    assert "handler=" in s


def test_safety_checks_huge_int(editor):
    """Test _is_safe_to_optimize defensive checks (Line 302-307)."""
    # Huge integer that exceeds PDF limits
    huge_int = 1152921504606846977  # 2^60 + 1

    safe = editor._is_safe_to_optimize("Tm", [huge_int], {"Tm"})
    assert safe is False


def test_safety_checks_stream_object(editor):
    """Test _is_safe_to_optimize defensive checks (Line 308-309)."""
    # Stream objects inside content streams are illegal/malformed
    # We mock PDFStream (it requires dict and data)
    mock_stream = PDFStream({}, b"")

    safe = editor._is_safe_to_optimize("Tm", [mock_stream], {"Tm"})
    assert safe is False

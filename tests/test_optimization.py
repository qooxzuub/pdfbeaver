import pytest

import pdfbeaver as beaver
from pdfbeaver import ProcessingOptions
from pdfbeaver.optimization import optimize_ops


def optimize_assertion(create_pdf, original_stream, expected_stream):
    pdf = create_pdf(original_stream)

    # Run with optimization
    beaver.process(pdf, options=ProcessingOptions(optimize=True))

    content = pdf.pages[0].Contents.read_bytes()

    def wsfix(x):
        return x.strip().replace(b"\n", b" ")

    assert wsfix(content) == wsfix(expected_stream)


def test_optimize_various(create_pdf):
    pairs = {
        (b"1 0 0 1 100 100 Tm 1 0 0 1 100 90 Tm (B) Tj", b"1 0 0 1 100 90 Tm (B) Tj"),
        (
            b"1 0 0 1 100 100 Tm (A) Tj 1 0 0 1 100 90 Tm (B) Tj",
            b"1 0 0 1 100 100 Tm (A) Tj 1 0 0 1 100 90 Tm (B) Tj",
        ),
        (
            b"1 0 0 1 100 100 Tm (A) Tj 1 0 0 1 100 90 Tm 10 5 Td (B) Tj",
            b"1 0 0 1 100 100 Tm (A) Tj 1 0 0 1 100 90 Tm 10 5 Td (B) Tj",
        ),
        (
            b"1 0 0 1 100 100 Tm (A) Tj 1 0 0 1 100 90 Tm 10 5 Td 25 50 Td (B) Tj",
            b"1 0 0 1 100 100 Tm (A) Tj 1 0 0 1 100 90 Tm 10 5 Td 25 50 Td (B) Tj",
        ),
        (
            b"1 0 0 1 100 90 Tm 10 5 Td 1 2 3 4 5 6 Tm 25 50 Td (B) Tj",
            b"1 2 3 4 5 6 Tm 25 50 Td (B) Tj",
        ),
    }
    for x, y in pairs:
        optimize_assertion(create_pdf, x, y)


def test_optimize_combine_arithmetic(create_pdf):
    """
    Test converting a sequential Tm (Set Matrix) into a Td (Move).

    Scenario:
    1. Tm set to 100, 100
    2. Tm set to 100, 90  (Effective move: 0, -10)

    The optimizer should remove the first Tm
    """
    stream = b"1 0 0 1 100 100 Tm 1 0 0 1 100 90 Tm (B) Tj"
    expected = b"1 0 0 1 100 90 Tm (B) Tj"
    pdf = create_pdf(stream)

    # Run with optimization
    opts = ProcessingOptions(optimize=True)
    beaver.process(pdf, options=opts)

    content = pdf.pages[0].Contents.read_bytes()
    assert content.strip() == expected.strip()


@pytest.mark.skip(
    reason=(
        "Optimization feature postponed: " "requires generic graphics state tracking"
    )
)
def test_optimize_remove_redundant_graphics_ops(create_pdf):
    """Test removing operations that set state to the current value."""
    # 0.5 g -> 0.5 g -> (Text)
    stream = b"0.5 g 0.5 g (Text) Tj"
    pdf = create_pdf(stream)

    beaver.process(pdf, options=ProcessingOptions(optimize=True))
    content = pdf.pages[0].Contents.read_bytes()

    # Should only appear once
    assert content.count(b"0.5 g") == 1


def test_optimize_tz_redundancy():
    """Test Tz (Horizontal Scaling) optimization (Lines 110, 122, 143, 163-170)."""
    # 1. Dead Store Elimination (Pass 1)
    # 100 Tz -> immediately overwritten by 90 Tz
    ops = [([100], "Tz"), ([90], "Tz"), (["Text"], "Tj")]  # Use it so 90 Tz isn't dead
    result = optimize_ops(ops)
    assert len(result) == 2
    assert result[0][0] == [90]  # 100 should be gone

    # 2. Redundancy Elimination (Pass 2)
    # 90 Tz -> 90 Tz (Same value)
    ops = [
        ([90], "Tz"),
        (["Text1"], "Tj"),
        ([90], "Tz"),  # Redundant
        (["Text2"], "Tj"),
    ]
    result = optimize_ops(ops)
    # Should keep first Tz, drop second
    # Result: Tz, Tj, Tj
    # Note: The second Tz is dropped because the state tracks current_tz = 90
    # and Tj does NOT invalidate current_tz (only current_tm)
    assert len(result) == 3
    assert result[0][1] == "Tz"
    assert result[1][1] == "Tj"
    assert result[2][1] == "Tj"


def test_optimize_tf_redundancy():
    """Test Tf (Font) redundancy (Line 182)."""
    # /F1 10 Tf -> /F1 10 Tf
    ops = [
        (["/F1", 10], "Tf"),
        (["Text1"], "Tj"),
        (["/F1", 10], "Tf"),  # Redundant
        (["Text2"], "Tj"),
    ]
    result = optimize_ops(ops)

    # Should drop the second Tf
    ops_only = [str(op) for _, op in result]
    assert ops_only.count("Tf") == 1


def test_handle_td_errors():
    """Test error handling in _handle_td (Lines 218-219)."""
    # Td requires numbers. Passing string should trigger exception handling.
    ops = [
        ([1, 0, 0, 1, 0, 0], "Tm"),  # Set initial valid matrix
        (["bad", "values"], "Td"),  # Trigger ValueError
    ]

    # Should not crash, just pass through
    result = optimize_ops(ops)
    assert len(result) == 2
    assert result[1][1] == "Td"

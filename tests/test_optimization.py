import pikepdf
import pytest

import pdfbeaver as beaver
from pdfbeaver import ProcessingOptions


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

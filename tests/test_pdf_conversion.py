import pikepdf
import pytest
from pdfminer.psparser import LIT, PSKeyword, PSLiteral

from pdfbeaver.utils.pdf_conversion import normalize_pdf_operand


def test_convert_pdfminer_types():
    """Verify pdfminer-specific types are converted to pikepdf equivalents."""

    # 1. PSLiteral -> pikepdf.Name
    lit = PSLiteral("F1")
    result = normalize_pdf_operand(lit)
    assert isinstance(result, pikepdf.Name)
    assert str(result) == "/F1"

    lit = PSLiteral(b"F1")
    result = normalize_pdf_operand(lit)
    assert isinstance(result, pikepdf.Name)
    assert str(result) == "/F1"

    # 2. PSKeyword -> pikepdf.Name
    kw = PSKeyword("SomeKey")
    result = normalize_pdf_operand(kw)
    assert isinstance(result, pikepdf.Name)
    assert str(result) == "/SomeKey"

    kw = PSKeyword(b"SomeKey")
    result = normalize_pdf_operand(kw)
    assert isinstance(result, pikepdf.Name)
    assert str(result) == "/SomeKey"


def test_recurse_lists():
    """Verify standard Python lists (used by pdfminer for arrays) are recursed."""
    # Input: List containing an integer and a PSLiteral
    input_list = [1, PSLiteral("A")]

    result = normalize_pdf_operand(input_list)

    assert isinstance(result, list)
    assert result[0] == 1
    # The inner item should have been converted
    assert isinstance(result[1], pikepdf.Name)
    assert str(result[1]) == "/A"


def test_passthrough_pikepdf_objects():
    """Verify that objects already in pikepdf format are left alone."""

    # 1. pikepdf.Array
    # Since the function doesn't explicitly check for pikepdf.Array,
    # it hits the default 'return operand'
    arr = pikepdf.Array([1, 2])
    result = normalize_pdf_operand(arr)
    assert isinstance(result, pikepdf.Array)
    assert result[0] == 1

    # 2. pikepdf.Name
    name = pikepdf.Name("/Existing")
    assert normalize_pdf_operand(name) == name


def test_passthrough_primitives():
    """Verify basic types pass through unchanged."""
    assert normalize_pdf_operand(42) == 42
    assert normalize_pdf_operand(3.14) == 3.14
    assert normalize_pdf_operand(b"raw bytes") == b"raw bytes"
    assert normalize_pdf_operand("string") == "string"

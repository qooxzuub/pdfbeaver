# tests/test_pdf_conversion.py
import numpy as np
import pikepdf
from pdfminer.psparser import PSKeyword, PSLiteral

from pdfbeaver.utils.pdf_conversion import (
    extract_string_bytes,
    font_name_to_string,
    miner_matrix_to_np,
    normalize_pdf_operand,
)


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


def test_extract_string_bytes_robustness():
    # 1. Standard Bytes
    assert extract_string_bytes(b"hello") == b"hello"

    # 2. String (Latin1 fallback)
    assert extract_string_bytes("hello") == b"hello"

    # 3. String (UTF-8 required)
    # Euro sign cannot be encoded in Latin1, triggers fallback or failure depending on impl
    # If your impl falls back to utf-8 on UnicodeEncodeError:
    euro = "€"
    assert extract_string_bytes(euro) == euro.encode("utf-8")

    # 4. Integers (Edge case often hit by parsing bugs)
    # Should probably convert to string bytes or fail gracefully
    assert extract_string_bytes(123) == b"123"


def test_font_name_cleaning():
    # 1. PSLiteral
    from pdfminer.psparser import PSLiteral

    assert font_name_to_string(PSLiteral(b"F1")) == "F1"

    # 2. Valid Name
    import pikepdf

    assert font_name_to_string(pikepdf.Name("/Helvetica")) == "Helvetica"

    # 3. Raw String
    assert font_name_to_string("/Times-Roman") == "Times-Roman"


# --- pdf_conversion.py Coverage ---


def test_miner_matrix_already_numpy():
    """Test line 13: Input is already a numpy array."""
    m = np.eye(3)
    # Should return identity unchanged
    res = miner_matrix_to_np(m)
    assert res is m
    assert np.array_equal(res, np.eye(3))


def test_font_name_with_string_literal():
    """Test line 74: PSLiteral containing a string (not bytes)."""
    # Most pdfminer versions use bytes, but we support strings too.
    # This hits the 'return name' at the end of the PSLiteral block.
    lit = PSLiteral("Helvetica")
    assert font_name_to_string(lit) == "Helvetica"


def test_extract_bytes_fallback_objects():
    """Test lines 53-65: Standard conversion and final fallback."""
    # 1. Standard Conversion (lines 59-60)
    # pikepdf.String behaves like bytes/str but isn't exactly them
    p_str = pikepdf.String("Test")
    assert extract_string_bytes(p_str) == b"Test"

    # 2. Final Fallback (line 65)
    # An object that cannot be converted to bytes
    obj = object()
    assert extract_string_bytes(obj) is obj

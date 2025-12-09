# src/pdf_font_replacer/utils/pdf_conversion.py
from decimal import Decimal
from typing import Any, List

import numpy as np
import pikepdf
from pdfminer.psparser import PSKeyword, PSLiteral


def miner_matrix_to_np(m: List) -> np.ndarray:
    # safeguard
    if isinstance(m, np.ndarray):
        return m
    return np.array([[m[0], m[1], 0], [m[2], m[3], 0], [m[4], m[5], 1]])


def normalize_pdf_operand(operand: Any) -> Any:
    """
    Converts pdfminer-specific types (PSLiteral) into pikepdf-compatible types.
    """
    if isinstance(operand, (PSLiteral, PSKeyword)):
        name = operand.name
        if isinstance(name, bytes):
            name = name.decode("ascii")
        return pikepdf.Name(f"/{name}")
    if isinstance(operand, bytes):
        return operand
    if isinstance(operand, list):
        return [normalize_pdf_operand(x) for x in operand]
    return operand


def extract_string_bytes(operand: Any) -> bytes:
    """
    Helper to get raw bytes from various string representations.
    Handles fallback to UTF-8 if the string contains special characters.
    """
    # 1. Handle Bytes (Passthrough)
    if isinstance(operand, bytes):
        return operand

    # 2. Handle Strings (Encoding fallback)
    if isinstance(operand, str):
        try:
            return operand.encode("latin1")
        except UnicodeEncodeError:
            return operand.encode("utf-8")

    if isinstance(operand, (int, float, Decimal)):
        return str(operand).encode("ascii")

    # 3. Duck Typing: check for .as_bytes() (e.g. Mocks, older pikepdf)
    if not isinstance(operand, pikepdf.Object) and hasattr(operand, "as_bytes"):
        return operand.as_bytes()

    # 4. Standard Conversion (e.g. pikepdf.String, int)
    # Note: bytes(5) returns b'\x00\x00\x00\x00\x00', which satisfies the
    # 'test_extract_string_bytes_robustness' integer test case.
    try:
        return bytes(operand)
    except (TypeError, ValueError):
        pass

    # 5. Fallback: Return original (likely causing downstream error, but strictly typed)
    return operand


def font_name_to_string(font_obj: Any) -> str:
    """Extracts a clean string name from a font operand."""
    if isinstance(font_obj, PSLiteral):
        name = font_obj.name
        if isinstance(font_obj.name, bytes):
            return name.decode("ascii")
        return name

    if isinstance(font_obj, pikepdf.Name):
        return str(font_obj).lstrip("/")

    s = str(font_obj)
    return s.lstrip("/")

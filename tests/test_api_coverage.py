from decimal import Decimal

import pikepdf
import pytest
from pdfminer.pdftypes import PDFStream
from pdfminer.psparser import PSLiteral

import pdfbeaver as beaver
from pdfbeaver.api import _convert_to_pdfminer_resources, _resolve_pages


def test_process_argument_validation():
    """Test lines 299-301: Validating the pdf argument."""
    with pytest.raises(TypeError, match="must be a pikepdf.Pdf"):
        beaver.process("not a pdf")


def test_page_selection_logic(create_pdf):
    """Test lines 312-334: _resolve_pages logic."""
    # Create a 3-page PDF
    pdf = create_pdf(b"(Page1) Tj")
    pdf.add_blank_page()  # Page 2
    pdf.add_blank_page()  # Page 3

    # 1. Select by Integer
    pages = _resolve_pages(pdf, 1)
    assert len(pages) == 1
    assert pages[0].index == 1

    # 2. Select by Page Object
    pages = _resolve_pages(pdf, pdf.pages[2])
    assert len(pages) == 1
    assert pages[0].index == 2

    # 3. Select by List of mixed types
    pages = _resolve_pages(pdf, [0, pdf.pages[2]])
    assert len(pages) == 2
    assert pages[0].index == 0
    assert pages[1].index == 2

    # 4. Error Case: List with bad type
    with pytest.raises(TypeError, match="Invalid item"):
        _resolve_pages(pdf, [0, "not a page"])

    # 5. Error Case: Bad argument type
    with pytest.raises(TypeError, match="Invalid type"):
        _resolve_pages(pdf, "bad argument")


def test_resource_conversion_complex_types():
    """Test lines 337-362: _convert_to_pdfminer_resources."""

    # Construct a complex pikepdf structure
    # {
    #   "/Name": /Value,
    #   "/Num": Decimal("1.5"),
    #   "/Arr": [/Item, "String"],
    #   "/Str": "SimpleString"
    # }

    p_dict = pikepdf.Dictionary(
        {
            "/Name": pikepdf.Name("/Value"),
            "/Num": Decimal("1.5"),
            "/Arr": pikepdf.Array([pikepdf.Name("/Item"), "String"]),
            "/Str": pikepdf.String("SimpleString"),
        }
    )

    # Run conversion
    converted = _convert_to_pdfminer_resources(p_dict)

    # Assertions
    assert isinstance(converted, dict)

    # Name conversion (PSLiteral object)
    # Note: convert strips slashes from keys
    assert "Name" in converted
    assert isinstance(converted["Name"], PSLiteral)
    assert converted["Name"].name == "Value"

    # Decimal conversion
    assert converted["Num"] == 1.5
    assert isinstance(converted["Num"], float)

    # Array conversion
    assert isinstance(converted["Arr"], list)
    assert isinstance(converted["Arr"][0], PSLiteral)
    assert converted["Arr"][1] == "String"


def test_resource_conversion_stream(create_pdf):
    """Test converting a pikepdf.Stream to a PDFStream."""
    pdf = create_pdf(b"")

    # Create a dummy stream resource
    s = pdf.make_stream(b"data")
    s.Type = pikepdf.Name("/Metadata")

    converted = _convert_to_pdfminer_resources(s)

    assert isinstance(converted, PDFStream)
    # Check data
    assert converted.get_data() == b"data"
    # Check attributes dict conversion
    assert "Type" in converted.attrs
    assert converted.attrs["Type"].name == "Metadata"


def test_invalid_content_streams_logging(caplog):
    """Test lines 270-276: Handling objects masquerading as streams."""
    # This tests the warning logger
    import logging

    # Create a dict that looks like a stream (has /Contents) but isn't one
    # This hits _handle_invalid_stream_like
    fake_item = pikepdf.Dictionary({"/Contents": []})

    # We can't easily trigger this via public API without mocking internals
    # because pikepdf usually handles the structure before we see it.
    # But we can test the private function directly.
    from pdfbeaver.api import _handle_invalid_stream_like

    # Case 1: Dict with Contents -> Returns contents
    res = _handle_invalid_stream_like(fake_item)
    assert res == []  # It processed the empty list

    # Case 2: Dict without Contents -> Warning
    bad_item = pikepdf.Dictionary({"/NotContents": 1})
    with caplog.at_level(logging.WARNING):
        res = _handle_invalid_stream_like(bad_item)
        assert res == []
        assert "Skipping invalid content item" in caplog.text

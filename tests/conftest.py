# tests/conftest.py

import binascii

import pikepdf
import pytest


def pytest_addoption(parser):
    """Add a custom CLI flag to run visual smoke tests."""
    parser.addoption(
        "--visual",
        action="store_true",
        default=False,
        help="Run visual smoke tests (downloads PDF)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests marked 'visual' unless the --visual flag is passed."""
    if config.getoption("--visual"):
        # If flag is present, run everything
        return

    skip_visual = pytest.mark.skip(reason="need --visual option to run")
    for item in items:
        if "visual" in item.keywords:
            item.add_marker(skip_visual)


##########
# FIXTURES
##########


@pytest.fixture
def create_pdf():
    """Factory fixture to create a simple 1-page PDF with specific content instructions."""

    def _make(content_stream_bytes: bytes):
        pdf = pikepdf.new()
        # Create a page
        page = pdf.add_blank_page(page_size=(100, 100))
        # Inject the raw content stream
        page.Contents = pdf.make_stream(content_stream_bytes)
        return pdf

    return _make


@pytest.fixture
def assert_stream_contains():
    """
    Returns a function that checks if a PDF content stream contains a specific
    text/operator combination, handling both Literal (foo) and Hex <666f6f> formats.

    Usage:
        assert_stream_contains(pdf_bytes, "Hello", "Tj")
    """

    def _check(stream_bytes: bytes, text: str, op: str = "Tj"):
        # 1. Literal Format: (Hello) Tj
        # Note: We assume pikepdf puts a space before the operator
        literal = f"({text}) {op}".encode("ascii")

        # 2. Hex Format: <48656c6c6f> Tj
        hex_val = binascii.hexlify(text.encode("ascii")).decode("ascii")
        hex_fmt = f"<{hex_val}> {op}".encode("ascii")

        # Check if either exists in the stream
        if literal in stream_bytes:
            return True
        if hex_fmt in stream_bytes:
            return True

        # Failure message
        raise AssertionError(
            f"Content not found.\n"
            f"Expected: {literal} OR {hex_fmt}\n"
            f"Found:    {stream_bytes}"
        )

    return _check

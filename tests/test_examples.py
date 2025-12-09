import sys
from pathlib import Path
from unittest.mock import patch

import pikepdf
import pytest

# Setup path to import examples
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
sys.path.append(str(EXAMPLES_DIR))

import dark_mode
import redactor
import trivial


@pytest.fixture
def input_pdf_path(tmp_path, create_pdf):
    stream = b"0 0 0 rg BT /F1 12 Tf 10 10 Td (This is a Secret message) Tj ET"
    pdf = create_pdf(stream)
    path = tmp_path / "input.pdf"
    pdf.save(path)
    return path


def test_trivial_main(input_pdf_path, tmp_path):
    output = tmp_path / "trivial.pdf"

    # Mock sys.argv
    argv = ["trivial.py", str(input_pdf_path), str(output)]

    with patch.object(sys, "argv", argv):
        trivial.main()

    assert output.exists()


def test_dark_mode_main(input_pdf_path, tmp_path):
    output = tmp_path / "dark.pdf"

    argv = ["dark_mode.py", str(input_pdf_path), str(output)]

    with patch.object(sys, "argv", argv):
        dark_mode.main()

    assert output.exists()
    # Check if content actually changed (background added)
    content = _get_first_page_content(output)
    assert b"re" in content  # Rectangle added


def test_redactor_main(input_pdf_path, tmp_path):
    output = tmp_path / "redacted.pdf"

    # Run with target "Secret"
    argv = ["redactor_boxes.py", str(input_pdf_path), str(output), "Secret"]

    with patch.object(sys, "argv", argv):
        redactor.main()

    assert output.exists()

    content = _get_first_page_content(output)
    assert b"(Secret)" not in content
    assert b"re" in content  # Black box added


def _get_first_page_content(filename):
    pdf = pikepdf.open(filename)
    page = pdf.pages[0]
    return page.Contents.read_bytes()

import shutil
import sys
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"
OUTPUT_DIR = PROJECT_ROOT / "smoke_outputs"
CACHE_DIR = PROJECT_ROOT / "tests" / "cache"

# Ensure examples can be imported
sys.path.append(str(EXAMPLES_DIR))
import dark_mode
import redactor  # <--- Corrected from redactor_boxes
import trivial

SAMPLE_PDF_URL = "https://www.irs.gov/pub/irs-pdf/f1040.pdf"


@pytest.fixture(scope="session")
def complex_pdf_path():
    """
    Returns path to a complex PDF (IRS Form 1040).
    Downloads it only if not present in tests/cache/.
    """
    if not CACHE_DIR.exists():
        CACHE_DIR.mkdir(parents=True)

    target_file = CACHE_DIR / "f1040.pdf"

    if target_file.exists():
        print(f"\n📦 Using cached PDF: {target_file}")
        return target_file

    print(f"\n⬇️  Downloading sample PDF to {target_file}...")
    try:
        opener = urllib.request.build_opener()
        opener.addheaders = [("User-agent", "Mozilla/5.0")]
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(SAMPLE_PDF_URL, target_file)
    except Exception as e:
        pytest.fail(f"Could not download sample PDF: {e}")

    return target_file


@pytest.fixture(scope="session", autouse=True)
def setup_output_dir():
    """Ensures the smoke_outputs directory exists and is clean."""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()
    yield
    print(f"\n\n✅ Visual Smoke Tests Complete. Inspect artifacts in: {OUTPUT_DIR}")


@pytest.mark.visual
def test_generate_smoke_artifacts(complex_pdf_path):
    """
    Runs examples against a real-world PDF.
    Asserts they run without error and produce output files.
    """

    # 1. Trivial Pass-Through
    out_trivial = OUTPUT_DIR / "01_trivial.pdf"
    argv = ["trivial.py", str(complex_pdf_path), str(out_trivial)]
    with patch.object(sys, "argv", argv):
        trivial.main()
    assert out_trivial.exists()

    # 2. Dark Mode
    out_dark = OUTPUT_DIR / "02_dark_mode.pdf"
    argv = ["dark_mode.py", str(complex_pdf_path), str(out_dark)]
    with patch.object(sys, "argv", argv):
        dark_mode.main()
    assert out_dark.exists()

    # 3. Redaction (Targeting "Income")
    out_redact = OUTPUT_DIR / "03_redacted.pdf"
    target = "tax"
    argv = ["redactor.py", str(complex_pdf_path), str(out_redact), target]
    with patch.object(sys, "argv", argv):
        redactor.main()  # <--- Corrected function call
    assert out_redact.exists()

    # --- Automated Sanity Checks ---
    import pikepdf

    # Check Redaction:
    with pikepdf.open(out_redact) as pdf:
        content = pdf.pages[0].Contents.read_bytes()
        assert b"(Income)" not in content
        assert b"re" in content

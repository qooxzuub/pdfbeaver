# pdfbeaver

> **A Python library for context-aware PDF content stream editing.**
<img align="right" width="100" src="https://raw.githubusercontent.com/qooxzuub/pdfbeaver/main/.github/assets/beaver-emoji.svg">

[![PyPI](https://img.shields.io/pypi/v/pdfbeaver)](https://pypi.org/project/pdfbeaver/)
[![CI](https://github.com/qooxzuub/pdfbeaver/actions/workflows/ci.yml/badge.svg)](https://github.com/qooxzuub/pdfbeaver/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/qooxzuub/pdfbeaver/graph/badge.svg)](https://codecov.io/gh/qooxzuub/pdfbeaver)
[![Documentation Status](https://readthedocs.org/projects/pdfbeaver/badge/?version=latest)](https://pdfbeaver.readthedocs.io/en/latest/?badge=latest)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pdfbeaver)](https://pypi.org/project/pdfbeaver/)

**beaver**: a helpful animal which manipulates water streams.

**pdfbeaver**: a helpful Python library for manipulating PDF content streams.

pdfbeaver is a Python library that bridges the gap between **reading** PDFs (calculating text positions, tracking graphics state) and **writing** PDFs (injecting operators, removing content). Using pdfbeaver, you can easily write PDF content stream filters in Python which are aware of "where you are on the page" at any given moment inside the content stream.

Example applications:

- change colors of PDF text and vector graphics
- redact PDF text content without disrupting the rest of the text
- optimize vector paths in PDF graphics
- replace fonts in a PDF file

It is built on top of [pdfminer.six](https://github.com/pdfminer/pdfminer.six) for content stream parsing/state tracking, and [pikepdf](https://github.com/pikepdf/pikepdf) (and [qpdf](https://github.com/pikepdf/pikepdf)) for PDF writing/manipulation.

## 🚀 Key Features

- **User-friendly API:** register stream editing methods using decorators.
- **Context-Aware Editing:** Modify operators based on the current graphics state (Font, Color, Matrix, CTM).
- **Safe Recursion:** Automatically traverses and modifies **Form XObjects**, ensuring nested content is treated exactly like page content.
- **State Tracking:** Tracks the cursor position ($x, y$) and transformation matrices ($Tm, CTM$) as you parse.
- **Peephole Optimization:** Includes passes to remove dead stores (unused graphics state updates) to keep output files small.

## 📦 Installation

```bash
pip install pdfbeaver
```

## ⚡ Quick Start

### 1. Simple Operator Replacement

Change all text color to Red.

```python
import pikepdf
import pdfbeaver

pdf = pikepdf.open("input.pdf")

@pdfbeaver.register("Tj", "TJ", "'", '"')
def make_text_red(op, operands, raw_bytes):
    # Return a sequence of instructions:
    # 1. Set RGB color to Red (1, 0, 0)
    # 2. Draw the original text
    return [
        ([1, 0, 0], "rg"),  # Non-stroking red
        ([1, 0, 0], "RG"),  # Stroking red
        raw_bytes           # Original text op
    ]

pdfbeaver.process(pdf)
pdf.save("output_red.pdf")
```

### 2. Context-Aware Modification (Redaction)

Delete text only if it appears in the top-left quadrant of the page.

```python
@pdfbeaver.register("Tj", "TJ")
def delete_top_left(context):
    x, y = pdfbeaver.extract_text_position(context.pre_input)[:2]
    if x < 300 and y > 400:
        return None
    return pdfbeaver.UNCHANGED # Pass through unchanged
```

### Flexible Signatures

The `@register` decorator inspects your function signature. You can include any of the following arguments in any order:

- `operands` (or `args`): List of arguments for the operator.
- `operator` (or `op`): The operator string (e.g. "Tj").
- `raw_bytes`: The original binary data for this instruction.
- `context`: The `StreamContext` object.
- `pdf`: The `pikepdf.Pdf` document.
- `page`: The `pikepdf.Page` object.

<!-- end docs-include -->

## 📚 Documentation

See [ReadTheDocs](https://pdfbeaver.readthedocs.io).

## 📄 License

MPL-2.0. See `LICENSE` for details.

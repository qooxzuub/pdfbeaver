#!/usr/bin/env python
import sys

import pikepdf

import pdfbeaver as editor

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} input.pdf output.pdf")
        sys.exit(1)

    with pikepdf.open(sys.argv[1]) as pdf:
        editor.process(pdf)
        pdf.save(sys.argv[2])

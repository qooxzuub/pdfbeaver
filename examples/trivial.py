#!/usr/bin/env python
import sys

import pikepdf

import pdfbeaver as editor


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} input.pdf output.pdf")
        sys.exit(1)

    with pikepdf.open(sys.argv[1]) as pdf:
        # Default registry is fine here since we want pass-through,
        # but explicit empty registry is safer for testing.
        editor.process(pdf, registry=editor.HandlerRegistry())
        pdf.save(sys.argv[2])


if __name__ == "__main__":
    main()

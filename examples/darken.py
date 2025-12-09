#!/usr/bin/env python

"""Darken colors in a PDF file"""

import sys

import pikepdf

import pdfbeaver as beaver

darkness = 0.5


@beaver.register("RG", "rg", "G", "g")
def darken_colors(operands, op):
    """Darken colors in a PDF color instruction, leaving white alone"""
    if min(operands) == 1:
        return beaver.UNCHANGED
    return [([darkness * float(x) for x in operands], op)]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} input.pdf output.pdf [darkness]")
        sys.exit(1)
    if len(sys.argv) == 4:
        darkness = float(sys.argv[3]) / 100

    with pikepdf.open(sys.argv[1]) as pdf:
        beaver.process(pdf)
        pdf.save(sys.argv[2])

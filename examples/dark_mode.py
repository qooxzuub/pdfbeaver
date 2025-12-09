#!/usr/bin/env python
"""Invert graphics and text in a PDF file and add black page backgrounds"""
import sys

import pikepdf

import pdfbeaver as beaver


@beaver.register("^")
def background(page):
    """Add a black background to a page"""
    box = page.mediabox
    rectangle_args = [box[0], box[1], abs(box[2] - box[0]), abs(box[3] - box[1])]
    return [(0, "g"), (rectangle_args, "re"), ([], "f"), (1, "g"), (1, "G")]


# Handle both Stroke (RG, G) and Fill (rg, g) colors
@beaver.register("RG", "rg", "G", "g")
def invert_colors(operands, op):
    """Invert color intructions"""
    return ([1 - float(x) for x in operands], op)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} input.pdf output.pdf")
        sys.exit(1)

    with pikepdf.open(sys.argv[1]) as pdf:
        beaver.process(pdf)  # Run on all pages
        pdf.save(sys.argv[2])

#!/usr/bin/env python
import sys

import pikepdf

import pdfbeaver as beaver


def main():
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} input.pdf output.pdf")
        sys.exit(1)

    registry = beaver.HandlerRegistry()

    @registry.register("^")
    def background(operands, context):
        # Add black background
        page = context.page
        box = page.mediabox
        rectangle_args = [box[0], box[1], abs(box[2] - box[0]), abs(box[3] - box[1])]
        return [(0, "g"), (rectangle_args, "re"), ([], "f"), (1, "g"), (1, "G")]

    @registry.register("RG", "rg", "G", "g")
    def invert_colors(operands, operator):
        return ([1 - float(x) for x in operands], operator)

    with pikepdf.open(sys.argv[1]) as pdf:
        beaver.process(pdf, registry=registry)
        pdf.save(sys.argv[2])


if __name__ == "__main__":
    main()

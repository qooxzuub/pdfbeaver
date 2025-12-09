Quickstart: Your First Edit
===========================

Welcome to ``pdfbeaver``. This library allows you to modify the internal content streams of a PDF file using Python functions.

Unlike libraries that treat PDFs as static images or simple strings, ``pdfbeaver`` lets you intercept the specific drawing commands (operators) that the PDF uses to render a page.

Installation
------------

.. code-block:: bash

   pip install pdfbeaver

The Concept: The Handler Registry
---------------------------------

The core concept of ``pdfbeaver`` is the **Registry**. You register Python functions to handle specific PDF operators. When the processor encounters that operator in the PDF stream, it calls your function.

* If you return new instructions, they replace the original.
* If you return an empty list ``[]``, the original instruction is deleted.
* If you return ``pdfbeaver.UNCHANGED``, the original instruction is kept.

Example: Dark Mode PDF
----------------------

Let's write a simple script that inverts all colors in a PDF (making white text on black background).

1. **Invert Colors:** We intercept ``rg`` (fill color) and ``RG`` (stroke color).
2. **Add Background:** We intercept the start of the page to draw a black rectangle.

.. code-block:: python

    import pikepdf
    import pdfbeaver as beaver

    # 1. Define the Logic
    @beaver.register("RG", "rg", "G", "g")
    def invert_colors(operands, op):
        # operands are a list of floats (0.0 to 1.0) representing color components
        # We simply invert them: 1 - x
        new_colors = [1.0 - float(x) for x in operands]
        return [(new_colors, op)]

    @beaver.register("^") # Special operator for "Start of Page"
    def add_background(page):
        # Draw a black rectangle over the whole page first
        box = page.mediabox
        rect = [box[0], box[1], float(box[2]), float(box[3])]
        return [
            ([0, 0, 0], "rg"), # Set Black
            (rect, "re"),      # Draw Rect
            "f"                # Fill
        ]

    # 2. Run the Processor
    pdf = pikepdf.open("input.pdf")
    beaver.process(pdf)
    pdf.save("dark_mode.pdf")

How it works
------------

When ``beaver.process(pdf)`` runs, it iterates through every content stream. When it sees an operator like ``0 0 0 rg`` (set black), it calls ``invert_colors``. Your function calculates ``1 - 0`` and returns ``1 1 1 rg`` (set white).

This happens extremely fast and preserves the vector nature of the PDF.
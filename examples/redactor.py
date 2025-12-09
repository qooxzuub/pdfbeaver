#!/usr/bin/env python
"""Redact text in a PDF file, by replacing PDF text instructions
containing a given target string with filled rectangles. Redacted text
is removed entirely from the page content stream, not merely covered
up. Other text on the page should not move.

This demonstrates state tracking functionality of pdfbeaver.

"""


import sys

import pikepdf

import pdfbeaver
from pdfbeaver.utils import extract_text_position

TARGET_WORD = "Secret"
PREVIEW = False

# --- The Handler ---

rects = []


@pdfbeaver.register("Td")
def remove_instruction():
    return []


def tj_offset(width, text_state):
    """Compute TJ offset (kerning value) for a given width"""
    h_scale = text_state.scaling / 100.0
    return -(width / (text_state.fontsize * h_scale)) * 1000


@pdfbeaver.register("Tj", "TJ")
def redact_smart(operands, context):
    """Redaction filter. This takes a text drawing instruction. If it
    is to be redacted, it is replaced with an equivalent spacer TJ
    instruction, and its redaction rectangle is recorded for later
    drawing. In all cases, its position in the output stream is fixed
    using explicit positioning instructions, so that it is unaffected
    by changes to other text instructions.

    """
    global rects

    text_state = context.pre_input["tstate"]

    # instruction for absolute positioning of text
    output_position_instruction = (text_state.matrix, "Tm")
    output_text_instruction = pdfbeaver.ORIGINAL_BYTES

    # naively test if we found the target (for proper text extraction, see pdfminer)
    if TARGET_WORD in str(operands[0]):
        # redact the output text and save the redaction rectangle

        start_pos = extract_text_position(context.pre_input)
        end_pos = extract_text_position(context.post_input)
        width = abs(end_pos[0] - start_pos[0])

        print(f"Redacting: {operands}")
        if not PREVIEW:
            # This moves the cursor past the redaction box to where the text ends
            output_text_instruction = ([[tj_offset(width, text_state)]], "TJ")

        # save redaction rectangle for drawing later on
        rects.append(
            [
                start_pos[0],
                start_pos[1] - (text_state.fontsize * 0.2),  # Baseline adjustment
                width,
                text_state.fontsize,
            ]
        )

    return [
        output_position_instruction,
        output_text_instruction,
    ]


@pdfbeaver.register("$")
def draw_rects():
    global rects
    rect_paths = [(x, "re") for x in rects]
    rects = []
    if PREVIEW:
        return [(0.5, "G"), *rect_paths, "s"]
    return [(0.5, "g"), *rect_paths, "f"]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            f"Usage: python {sys.argv[0]} input.pdf output.pdf [<target_word>] [preview]"
        )
        sys.exit(1)

    if len(sys.argv) > 3:
        TARGET_WORD = sys.argv[3]
    if len(sys.argv) > 4:
        PREVIEW = True

    pdf = pikepdf.open(sys.argv[1])
    pdfbeaver.process(pdf)
    pdf.save(sys.argv[2])

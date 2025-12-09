#!/usr/bin/env python
import sys

import pikepdf

import pdfbeaver
from pdfbeaver.utils import extract_text_position


def main():
    if len(sys.argv) < 3:
        print(
            f"Usage: python {sys.argv[0]} input.pdf output.pdf [target_word] [preview]"
        )
        sys.exit(1)

    target_word = sys.argv[3] if len(sys.argv) > 3 else "Secret"
    preview = len(sys.argv) > 4

    pdf = pikepdf.open(sys.argv[1])

    # --- Local State & Registry ---
    registry = pdfbeaver.HandlerRegistry()
    rects = []

    def tj_offset(width, text_state):
        h_scale = text_state.scaling / 100.0
        return -(width / (text_state.fontsize * h_scale)) * 1000

    @registry.register("Td")
    def remove_instruction(operands, context):
        return []

    @registry.register("Tj", "TJ")
    def redact_smart(operands, context):
        text_state = context.pre_input["tstate"]

        # Determine content string
        # (Simplified check; real code might need to handle encoding/TJ arrays)
        content_str = str(operands[0])

        if target_word in content_str:
            start_pos = extract_text_position(context.pre_input)
            end_pos = extract_text_position(context.post_input)
            width = abs(end_pos[0] - start_pos[0])
            print(f"Redacting: {operands}")

            rects.append(
                [
                    start_pos[0],
                    start_pos[1] - (text_state.fontsize * 0.2),
                    width,
                    text_state.fontsize * text_state.matrix[3],
                ]
            )

            if not preview:
                # Replace text with spacer
                offset = tj_offset(width, text_state)
                # Ensure we explicitly reset matrix to avoid drift
                return [(text_state.matrix, "Tm"), ([[offset]], "TJ")]

        # If not modifying, we still return explicit Tm for safety in this specific script
        return [(text_state.matrix, "Tm"), pdfbeaver.ORIGINAL_BYTES]

    @registry.register("$")
    def draw_rects(operands, context):
        nonlocal rects
        if not rects:
            return []

        cmds = [(0.5, "g")] if not preview else [(0.5, "G")]
        cmds.append(([1, 0, 0, 1, 0, 0], "cm"))
        for r in rects:
            cmds.append((r, "re"))

        cmds.append("f" if not preview else "s")
        rects = []  # Clear for next page
        return cmds

    # Pass the local registry!
    pdfbeaver.process(pdf, registry=registry)
    pdf.save(sys.argv[2])


if __name__ == "__main__":
    main()

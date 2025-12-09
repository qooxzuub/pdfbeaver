Tutorial: Robust Text Redaction
===============================

Redacting text in a PDF is more complex than it seems. You cannot simply draw a black box "over" the text because the text underneath remains searchable and selectable. You must **remove** the text instructions and **replace** them with a black box.

The "Defer and Draw" Strategy
-----------------------------

A common mistake is trying to draw the black box immediately when you find the text. This is difficult because PDF separates "Text Mode" (where you can write letters) from "Graphics Mode" (where you can draw shapes). Switching back and forth breaks the stream state.

A more robust strategy is:

1.  **Process Text:** Iterate through the stream. If we find the target word:
    * Calculate where it is.
    * Save those coordinates to a list.
    * **Replace** the text operator with a "Spacer" (an invisible move) so the cursor ends up in the correct place for the *next* word.
2.  **Draw Later:** At the very end of the stream, draw all the collected black boxes at once.

Step 1: State & Geometry
------------------------

We use a simple global list to store our redaction targets.

.. code-block:: python

    rects = []

    def tj_offset(width, text_state):
        """
        Calculates how much to move the cursor to skip over the redacted text.
        TJ units are 1000 per em.
        """
        h_scale = text_state.scaling / 100.0
        return -(width / (text_state.fontsize * h_scale)) * 1000

Step 2: The Text Handler
------------------------

This handler does three critical things:
1.  **Stabilizes Position:** It explicitly sets the text matrix (``Tm``) to the start of the line. This prevents "drift" if our calculations are slightly off.
2.  **Calculates Width:** It uses ``extract_text_position`` to find the physical width of the text.
3.  **Substitutes:** It replaces the drawing command (``Tj``) with a spacing command (``TJ``).

.. code-block:: python

    import pdfbeaver
    from pdfbeaver.utils import extract_text_position

    TARGET_WORD = "Secret"

    @pdfbeaver.register("Tj", "TJ")
    def redact_smart(operands, context):
        global rects
        
        # 1. Get State
        text_state = context.pre_input["tstate"]

        # 2. Naive Check (String matching)
        # Note: Production code should handle encoding/ligatures here.
        if TARGET_WORD not in str(operands[0]):
             # Even if we don't redact, we explicitly set Tm to keep alignment rock solid
             return [
                 (text_state.matrix, "Tm"),
                 pdfbeaver.ORIGINAL_BYTES
             ]

        # 3. Calculate Geometry
        start_pos = extract_text_position(context.pre_input)
        end_pos = extract_text_position(context.post_input)
        width = abs(end_pos[0] - start_pos[0])

        print(f"Redacting: {operands}")

        # 4. Create the "Spacer"
        # Replaces the text with an empty movement of the same width
        spacer_cmd = ([[tj_offset(width, text_state)]], "TJ")

        # 5. Save the Box for later
        rects.append([
            start_pos[0],
            start_pos[1] - (text_state.fontsize * 0.2), # Baseline adjustment
            width,
            text_state.fontsize,
        ])

        # 6. Return instructions
        # We return the Matrix Reset + The Spacer
        return [
            (text_state.matrix, "Tm"),
            spacer_cmd
        ]

Step 3: The End-of-Stream Hook
------------------------------

``pdfbeaver`` provides a special virtual operator ``$`` that triggers at the end of a content stream. This is the perfect place to draw our graphics, as we are guaranteed to be outside of any text object.

.. code-block:: python

    @pdfbeaver.register("$")
    def draw_rects():
        global rects
        
        # Create a list of 're' (Rectangle) commands
        rect_paths = [(x, "re") for x in rects]
        
        # Clear the buffer for the next page
        rects = []
        
        # Return the graphics instructions
        # 0.5 g = Set Gray Level
        # f = Fill
        return [(0.5, "g"), *rect_paths, "f"]

Full Script
-----------

Here is the complete, working script combining these concepts.

.. code-block:: python

    #!/usr/bin/env python
    import sys
    import pikepdf
    import pdfbeaver
    from pdfbeaver.utils import extract_text_position

    TARGET_WORD = "Secret"
    rects = []

    # Helper: Convert width to PDF text units
    def tj_offset(width, text_state):
        h_scale = text_state.scaling / 100.0
        return -(width / (text_state.fontsize * h_scale)) * 1000

    # Handler: Removes explicit text positioning (Td) to force reliance on Tm
    @pdfbeaver.register("Td")
    def remove_instruction():
        return []

    # Handler: Processes Text
    @pdfbeaver.register("Tj", "TJ")
    def redact_smart(operands, context):
        global rects
        text_state = context.pre_input["tstate"]

        # 1. Enforce Absolute Positioning
        output_position_instruction = (text_state.matrix, "Tm")
        output_text_instruction = pdfbeaver.ORIGINAL_BYTES

        # 2. Check for Redaction
        if TARGET_WORD in str(operands[0]):
            start_pos = extract_text_position(context.pre_input)
            end_pos = extract_text_position(context.post_input)
            width = abs(end_pos[0] - start_pos[0])

            # Replace text with spacer
            output_text_instruction = ([[tj_offset(width, text_state)]], "TJ")

            # Buffer the rectangle
            rects.append([
                start_pos[0],
                start_pos[1] - (text_state.fontsize * 0.2),
                width,
                text_state.fontsize,
            ])

        return [output_position_instruction, output_text_instruction]

    # Handler: Draws Buffered Rectangles at End of Stream
    @pdfbeaver.register("$")
    def draw_rects():
        global rects
        if not rects: return []
        
        rect_paths = [(x, "re") for x in rects]
        rects = []
        return [(0, "g"), *rect_paths, "f"]

    # Main Execution
    if __name__ == "__main__":
        pdf = pikepdf.open(sys.argv[1])
        pdfbeaver.process(pdf)
        pdf.save(sys.argv[2])
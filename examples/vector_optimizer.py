#!/usr/bin/env python
import math
import sys
from typing import List, Tuple

import pikepdf

import pdfbeaver as editor

# --- 1. The Math (Ramer-Douglas-Peucker) ---


def perpendicular_distance(point, line_start, line_end):
    """Calculates distance from point to the line segment."""
    if line_start == line_end:
        return math.hypot(point[0] - line_start[0], point[1] - line_start[1])

    x, y = point
    x1, y1 = line_start
    x2, y2 = line_end

    nom = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
    denom = math.hypot(y2 - y1, x2 - x1)
    return nom / denom


def simplify_path(
    points: List[Tuple[float, float]], epsilon: float
) -> List[Tuple[float, float]]:
    """Recursively simplifies a list of (x,y) points."""
    if len(points) < 3:
        return points

    dmax = 0.0
    index = 0
    end = len(points) - 1

    for i in range(1, end):
        d = perpendicular_distance(points[i], points[0], points[end])
        if d > dmax:
            index = i
            dmax = d

    if dmax > epsilon:
        rec_results1 = simplify_path(points[: index + 1], epsilon)
        rec_results2 = simplify_path(points[index:], epsilon)
        return rec_results1[:-1] + rec_results2
    else:
        return [points[0], points[end]]


# --- 2. The Logic Class ---


class VectorOptimizer:
    """
    A stateful optimizer that buffers path operators (m, l) and simplifies them.
    """

    def __init__(self, epsilon=2.0):
        self.epsilon = epsilon
        self.buffer = []  # Stores (x, y) tuples

        # We create a specific registry for this instance because we need
        # to bind handlers to 'self.buffer'
        self.registry = editor.HandlerRegistry()
        self._register_handlers()

    def _register_handlers(self):
        # Intercept Move (start of path)
        @self.registry.register("m")
        def handle_move(operands, raw_bytes):
            prev_ops = self._flush_buffer()  # Previous path ends, new one begins
            try:
                x, y = float(operands[0]), float(operands[1])
                self.buffer = [(x, y)]
            except (ValueError, TypeError):
                return prev_ops + [raw_bytes]
            return prev_ops  # Swallow the 'm', we write it later

        # Intercept Line (add to path)
        @self.registry.register("l")
        def handle_line(operands, raw_bytes):
            if not self.buffer:
                return [raw_bytes]  # Invalid state (l without m)
            try:
                x, y = float(operands[0]), float(operands[1])
                self.buffer.append((x, y))
            except (ValueError, TypeError):
                pass
            return []  # Swallow the 'l'

        # Intercept Paint/End (Trigger optimization)
        # S=Stroke, f=Fill, s=Close+Stroke, etc.
        @self.registry.register("S", "f", "F", "s", "B", "b", "n")
        def handle_paint(operands, op):
            # Flush the optimized path, then write the paint operator
            return self._flush_buffer() + [([], op)]

    def _flush_buffer(self):
        """Simplifies the buffered path and generates new PDF ops."""
        if not self.buffer:
            return []

        # Run Algorithm
        simplified = simplify_path(self.buffer, self.epsilon)

        ops = []
        if simplified:
            # First point is always 'm'
            ops.append(([simplified[0][0], simplified[0][1]], "m"))
            # Rest are 'l'
            for p in simplified[1:]:
                ops.append(([p[0], p[1]], "l"))

        self.buffer = []
        return ops


# --- 3. Main Script ---

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python vector_optimizer.py input.pdf output.pdf [epsilon]")
        sys.exit(1)

    input_pdf = sys.argv[1]
    output_pdf = sys.argv[2]
    epsilon = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0

    print(f"Optimizing vectors in {input_pdf} with epsilon={epsilon}...")

    with pikepdf.open(input_pdf) as pdf:
        optimizer = VectorOptimizer(epsilon)
        for i in range(len(pdf.pages)):
            # Use the high-level API, but pass our custom registry
            print(f"Processing page {i+1}")
            editor.process(pdf, registry=optimizer.registry, page=i)

        pdf.save(output_pdf)
    print("Done.")

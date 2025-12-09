Tutorial: Optimizing Vector Graphics
====================================

``pdfbeaver`` isn't limited to one-to-one replacements. You can create **Stateful Handlers** that buffer multiple operators, analyze them, and write back a completely different set of instructions.

Use Case: Path Simplification
-----------------------------

Imagine a PDF map with a coastline defined by thousands of tiny line segments. This makes the file large and slow to render. We can use the **Ramer-Douglas-Peucker** algorithm to simplify these lines.

Strategies for Stateful Handlers
--------------------------------

Instead of a simple function, we can register methods of a class. This allows us to maintain a ``self.buffer``.

1. **Intercept** ``m`` (move to) and ``l`` (line to) operators. Store the points in a list.
2. **Intercept** painting operators (``S``, ``f``). This signals the end of a path.
3. **Process** the list of points (simplify them).
4. **Flush** the new, shorter list of operators to the stream.

.. code-block:: python

    class VectorOptimizer:
        def __init__(self):
            self.buffer = [] # Store (x, y) points
            
            # Create a registry just for this job
            self.registry = beaver.HandlerRegistry()

            # Register methods
            self.registry.register("m", "l")(self.handle_path)
            self.registry.register("S", "f")(self.handle_paint)

        def handle_path(self, operands, op):
            # Don't write anything yet! Just store the data.
            x, y = float(operands[0]), float(operands[1])
            self.buffer.append((x, y))
            return [] # Delete the original operator from the stream

        def handle_paint(self, operands, op):
            # The path is finished. Optimize it now.
            if len(self.buffer) > 100:
                simplified_points = self.simplify(self.buffer)
                
                # Reconstruct operators
                new_ops = []
                new_ops.append(([simplified_points[0]], "m"))
                for p in simplified_points[1:]:
                     new_ops.append(([p], "l"))
                
                # Add the paint operator at the end
                new_ops.append(([], op))
                
                self.buffer = []
                return new_ops
            
            # If path was short, just return originals (logic omitted for brevity)
            return beaver.UNCHANGED

        def simplify(self, points):
            # Implementation of Ramer-Douglas-Peucker...
            return points

    # Running it
    pdf = pikepdf.open("map.pdf")
    optimizer = VectorOptimizer()
    
    # Pass the custom registry
    beaver.process(pdf, registry=optimizer.registry)
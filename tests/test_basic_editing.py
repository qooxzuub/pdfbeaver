# tests/test_basic_editing.py

import pdfbeaver as beaver


def test_replace_text_operator(create_pdf, assert_stream_contains):
    """Test replacing one operator with another."""
    pdf = create_pdf(b"(Hello) Tj")

    registry = beaver.HandlerRegistry()

    @registry.register("Tj")
    def replace_hello(operands, context):
        # FIX: Do not include parens in the string value.
        # pikepdf handles the syntax. Just return the text "World".
        return [("World", "Tj")]

    beaver.process(pdf, registry=registry)

    content = pdf.pages[0].Contents.read_bytes()

    # Use our helper to check for "World" + "Tj"
    assert_stream_contains(content, "World", "Tj")

    # Ensure original is gone (naive check is fine for deletion)
    assert b"(Hello)" not in content and b"<48656c6c6f>" not in content


def test_delete_operator(create_pdf):
    """Test removing an operator by returning an empty list."""
    # Use hex for input just to be sure we handle mixed inputs
    pdf = create_pdf(b"10 10 Td (DeleteMe) Tj")

    registry = beaver.HandlerRegistry()

    @registry.register("Tj")
    def delete_text(operands, context):
        return []

    beaver.process(pdf, registry=registry)

    content = pdf.pages[0].Contents.read_bytes()
    assert b"10 10 Td" in content
    assert b"DeleteMe" not in content


def test_pass_through_unchanged(create_pdf, assert_stream_contains):
    """Test returning UNCHANGED flag."""
    pdf = create_pdf(b"(KeepMe) Tj")

    registry = beaver.HandlerRegistry()

    @registry.register("Tj")
    def keep_it(operands, context):
        return beaver.UNCHANGED

    beaver.process(pdf, registry=registry)

    content = pdf.pages[0].Contents.read_bytes()
    assert_stream_contains(content, "KeepMe", "Tj")


def test_insert_multiple_ops(create_pdf, assert_stream_contains):
    """Test replacing 1 operator with 3 (expansion)."""
    pdf = create_pdf(b"(Start) Tj")

    registry = beaver.HandlerRegistry()

    @registry.register("Tj")
    def expand(operands, context):
        return [(0.5, "g"), ("Middle", "Tj"), (0, "g")]  # Again, no parens in value

    beaver.process(pdf, registry=registry)

    content = pdf.pages[0].Contents.read_bytes()

    # Check parts
    # Note: float serialization might vary (0.5 vs .5), so loose check for numbers is safer
    assert b"0.5 g" in content or b".5 g" in content
    assert_stream_contains(content, "Middle", "Tj")
    assert b"0 g" in content

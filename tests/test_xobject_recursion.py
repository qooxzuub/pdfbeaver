import pikepdf

import pdfbeaver as beaver


def test_recurse_into_xobject(create_pdf, assert_stream_contains):
    """Verify that we modify text inside a Form XObject."""
    # 1. Create a basic PDF
    pdf = create_pdf(b"/Form1 Do")  # The page just says "Draw Form1"
    page = pdf.pages[0]

    # 2. Create a Form XObject containing the text "Hidden"
    # In pikepdf, a Form XObject is just a Stream with Type=XObject, Subtype=Form
    xobj_stream = b"(Hidden) Tj"
    xobj = pdf.make_stream(xobj_stream)
    xobj.Type = pikepdf.Name("/XObject")
    xobj.Subtype = pikepdf.Name("/Form")
    xobj.BBox = [0, 0, 100, 100]

    # 3. Attach it to the page resources
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Form1=xobj))

    # 4. Run Processor
    registry = beaver.HandlerRegistry()

    @registry.register("Tj")
    def redact(operands, context):
        return [("Found", "Tj")]

    # By default, recurse_xobjects=True
    beaver.process(pdf, registry=registry)

    # 5. Assertions
    # The XObject stream itself should be modified
    xobj_content = xobj.read_bytes()
    assert_stream_contains(xobj_content, "Found", "Tj")
    assert b"Hidden" not in xobj_content


def test_disable_recursion(create_pdf, assert_stream_contains):
    """Verify that recurse_xobjects=False prevents modification."""
    pdf = create_pdf(b"/Form1 Do")
    page = pdf.pages[0]

    xobj = pdf.make_stream(b"(Hidden) Tj")
    xobj.Type = pikepdf.Name("/XObject")
    xobj.Subtype = pikepdf.Name("/Form")
    xobj.BBox = [0, 0, 100, 100]

    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Form1=xobj))

    registry = beaver.HandlerRegistry()

    @registry.register("Tj")
    def redact(operands, context):
        return [("Found", "Tj")]

    # DISABLE recursion
    options = beaver.ProcessingOptions(recurse_xobjects=False)
    beaver.process(pdf, registry=registry, options=options)

    # 5. Assertions
    xobj_content = xobj.read_bytes()
    assert b"(Hidden) Tj" in xobj_content
    assert b"Found" not in xobj_content

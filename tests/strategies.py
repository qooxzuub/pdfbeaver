# tests/strategies.py
from hypothesis import strategies as st

# 1. Basic Types
# PDF numbers can be ints or floats. We limit range to avoid overflow errors in naive math.
pdf_float = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
)
pdf_int = st.integers(min_value=-10000, max_value=10000)
pdf_scalar = st.one_of(pdf_float, pdf_int)

# PDF Names (e.g., /F1)
# simplified: just strings starting with /
pdf_name = st.text(
    min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))
).map(lambda x: "/" + x)

# PDF Strings
pdf_string = st.text(min_size=0, max_size=50).map(lambda x: x.encode("ascii", "ignore"))

# 2. Operands
# An operand can be a number, a name, a string, or a list (array)
# We use a recursive definition for arrays, but keep it shallow for speed
basic_operand = st.one_of(pdf_scalar, pdf_name, pdf_string)
pdf_operand = st.recursive(
    basic_operand, lambda children: st.lists(children, max_size=5), max_leaves=10
)
pdf_operands_list = st.lists(pdf_operand, max_size=8)

# 3. Operators
# We want to hit your specific optimization logic (Tm, Td) often, but also random garbage
known_ops = st.sampled_from(
    ["Tm", "Td", "TD", "Tf", "Tj", "TJ", "q", "Q", "BT", "ET", "g", "RG", "re"]
)
random_ops = st.text(
    min_size=1, max_size=4, alphabet=st.characters(whitelist_categories=("L",))
)
pdf_operator = st.one_of(known_ops, random_ops)

# 4. Structures
# A single instruction tuple: ([operands], "Op")
pdf_instruction = st.tuples(pdf_operands_list, pdf_operator)

# A stream of instructions
pdf_stream_instructions = st.lists(pdf_instruction, max_size=50)


# A "Step" dictionary (what state_iterator yields)
# We need to ensure the structure matches what editor.py expects
@st.composite
def pdf_step(draw):
    op = draw(pdf_operator)
    operands = draw(pdf_operands_list)
    raw = b"mock_raw"

    # Minimal state object
    return {
        "operator": op,
        "operands": operands,
        "raw_bytes": raw,
        "state": {
            # We can expand this to fuzz state injection later if needed
            "ctm": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        },
    }


pdf_step_stream = st.lists(pdf_step(), max_size=50)

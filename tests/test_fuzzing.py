# tests/test_fuzzing.py
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pdfbeaver.editor import StreamEditor
from pdfbeaver.optimization import optimize_ops
from pdfbeaver.registry import HandlerRegistry
from pdfbeaver.state_tracker import StateTracker

from .strategies import pdf_step_stream, pdf_stream_instructions

# Define a "Dev Profile" for settings to keep things fast
FAST_SETTINGS = settings(
    max_examples=50,  # Run only 50 random cases (down from 500)
    deadline=None,  # Don't fail if a run takes >200ms
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

# --- Fuzzing the Optimizer ---


@given(ops=pdf_stream_instructions)
@FAST_SETTINGS
def test_fuzz_optimizer_no_crashes(ops):
    """
    Property: The optimizer should never crash.
    """
    try:
        result = optimize_ops(ops)
    except Exception as e:
        pytest.fail(f"Optimizer crashed on input: {ops}\nError: {e}")

    assert isinstance(result, list)


@given(ops=pdf_stream_instructions)
@FAST_SETTINGS
def test_fuzz_optimizer_structure_preservation(ops):
    """
    Property: Optimization output should be valid tuples.
    """
    result = optimize_ops(ops)

    for item in result:
        assert isinstance(item, tuple)
        assert len(item) == 2
        assert isinstance(item[0], list)


# --- Fuzzing the Stream Editor ---


@given(steps=pdf_step_stream)
@FAST_SETTINGS
def test_fuzz_editor_pipeline(steps):
    """
    Property: The StreamEditor should ingest any sequence without crashing.
    """
    registry = HandlerRegistry()
    tracker = StateTracker()

    # Mock the iterator
    editor = StreamEditor(iter(steps), registry, tracker)

    try:
        output_bytes = editor.process()
    except Exception as e:
        pytest.fail(f"Editor crashed on steps: {steps}\nError: {e}")

    assert isinstance(output_bytes, bytes)


@given(
    # Generate a base matrix [a, b, c, d, e, f]
    tm_base=st.lists(st.floats(min_value=-100, max_value=100), min_size=6, max_size=6),
    # Generate a small delta to ensure the second matrix is "close" enough
    delta=st.lists(
        st.floats(min_value=-0.00001, max_value=0.00001), min_size=6, max_size=6
    ),
    # Generate a translation (e, f) that is large enough to be interesting
    trans=st.lists(st.floats(min_value=-100, max_value=100), min_size=2, max_size=2),
)
@FAST_SETTINGS
def test_fuzz_optimization_logic_tm_consolidation(tm_base, delta, trans):
    """
    Property: If we have two consecutive Tm operators, the first one is a Dead Store.
    The optimizer should reduce this sequence to a single Tm (the second one).
    """
    # 1. Construct Tm1
    tm1_ops = tm_base

    # 2. Construct Tm2
    tm2_ops = [
        tm_base[0] + delta[0],
        tm_base[1] + delta[1],
        tm_base[2] + delta[2],
        tm_base[3] + delta[3],
        tm_base[4] + trans[0],
        tm_base[5] + trans[1],
    ]

    input_stream = [(tm1_ops, "Tm"), (tm2_ops, "Tm")]

    # 3. Run Optimizer
    result = optimize_ops(input_stream)

    # 4. Assertions
    # Pass 1 (Dead Store) should detect Tm1 is useless and remove it.
    assert len(result) == 1

    # The remaining operator should be the second one (Tm2)
    assert str(result[0][1]) == "Tm"
    # Check X translation matches Tm2 (approximate float check)
    assert abs(result[0][0][4] - tm2_ops[4]) < 0.001

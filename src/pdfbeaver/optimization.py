# src/pdfbeaver/optimization.py
"""
Logic for optimizing PDF content streams (peephole optimization).
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from pikepdf import Operator

logger = logging.getLogger(__name__)

TZ_TOL = 0.001
TF_TOL = 0.001
TM_TOL = 0.0001
ROUNDING_PLACES = 4

CONVERSION_ERRORS = (ValueError, IndexError, TypeError, OverflowError)

# SIMPLE_STATE_OPS = {
#     "g", "G", "rg", "RG", "k", "K",  # Colors
#     "w", "J", "j", "M",              # Line attributes
#     "i", "ri"                        # Flatness, Rendering Intent
# }


@dataclass
class OptimizerState:
    """Tracks the current graphics state during the forward optimization pass."""

    current_tz: float = 100.0
    current_tf_name: Optional[str] = None
    current_tf_size: Optional[float] = None
    current_tm: Optional[List[float]] = None
    simple_states: Dict[str, List[Any]] = field(default_factory=dict)


def optimize_ops(ops: List[Tuple[List[Any], Any]]) -> List[Tuple[List[Any], Any]]:
    """
    Orchestrates the two-pass optimization strategy.

    1. **Reverse Pass:** Removes 'Dead Stores' (values set but overwritten before use).
    2. **Forward Pass:** Removes redundant sets and converts absolute matrices (Tm)
       to relative moves (Td) where possible.
    """
    if not ops:
        return []

    # Pass 1: Reverse Dead-Store Elimination
    ops_pass1 = _remove_dead_stores(ops)

    # Pass 2: Forward Redundancy & Consolidation
    return _consolidate_redundant_ops(ops_pass1)


# --- Metadata ---
# The Editor uses this to automatically buffer these operators,
# ensuring the optimizer sees the full context it needs.
optimize_ops.relevant_operators = {
    "Tm",
    "Td",
    "TD",
    "q",
    "Q",
    "cm",
    "BT",
    "ET",
    "Tf",
    "Tz",
    # *SIMPLE_STATE_OPS,
}


def _remove_dead_stores(
    ops: List[Tuple[List[Any], Any]],
) -> List[Tuple[List[Any], Any]]:
    """
    Backward pass: removes operations that set a state which is immediately
    overwritten without being used.
    """
    rev_optimized = []
    future_overwrites: Set[str] = set()

    for operands, operator in reversed(ops):
        op_name = str(operator)

        # Barrier: Text operations consume all state
        if op_name in ["Tj", "TJ", "'", '"']:
            future_overwrites.clear()
            rev_optimized.append((operands, operator))
            continue

        if _is_dead_store(op_name, future_overwrites):
            continue

        _update_overwrites(op_name, future_overwrites)
        rev_optimized.append((operands, operator))

    return list(reversed(rev_optimized))


def _is_dead_store(op_name: str, future_overwrites: Set[str]) -> bool:
    """Checks if the current operator is overwritten by a future one."""
    if op_name == "Tm":
        return "Tm" in future_overwrites
    if op_name == "Td":
        # Td is relative, but if a Tm follows, Td is useless (absolute reset)
        return "Tm" in future_overwrites
    if op_name == "Tz":
        return "Tz" in future_overwrites
    if op_name == "Tf":
        return "Tf" in future_overwrites
    return False


def _update_overwrites(op_name: str, future_overwrites: Set[str]):
    """Updates the set of overwritten states based on the current operator."""
    if op_name == "Tm":
        future_overwrites.add("Tm")
        future_overwrites.add("Td")  # Tm resets translation too
    elif op_name == "Tz":
        future_overwrites.add("Tz")
    elif op_name == "Tf":
        future_overwrites.add("Tf")


def _consolidate_redundant_ops(
    ops: List[Tuple[List[Any], Any]],
) -> List[Tuple[List[Any], Any]]:
    """
    Forward pass:
    1. Removes operations that set the state to its current value.
    2. Converts Tm -> Td (Absolute -> Relative) to save bytes.
    """
    final_optimized = []
    state = OptimizerState()

    for operands, operator in ops:
        op_name = str(operator)
        result = None

        if op_name == "Tz":
            result = _handle_tz(operands, operator, state)
        elif op_name == "Tf":
            result = _handle_tf(operands, operator, state)
        elif op_name == "Tm":
            result = _handle_tm(operands, operator, state)
        elif op_name == "Td":
            result = _handle_td(operands, operator, state)
        elif op_name == "BT":
            state.current_tm = None
            result = (operands, operator)
        else:
            result = (operands, operator)

        if result:
            final_optimized.append(result)

    return final_optimized


def _handle_tz(operands, operator, state: OptimizerState):
    try:
        new_tz = float(operands[0])
        if abs(new_tz - state.current_tz) < TZ_TOL:
            return None  # Redundant
        state.current_tz = new_tz
        return (operands, operator)
    except CONVERSION_ERRORS:
        return (operands, operator)


def _handle_tf(operands, operator, state: OptimizerState):
    try:
        new_name = str(operands[0])
        new_size = float(operands[1])
        if (
            new_name == state.current_tf_name
            and state.current_tf_size is not None
            and abs(new_size - state.current_tf_size) < TF_TOL
        ):
            return None  # Redundant
        state.current_tf_name = new_name
        state.current_tf_size = new_size
        return (operands, operator)
    except (ValueError, IndexError, TypeError):
        return (operands, operator)


def _handle_tm(operands, operator, state: OptimizerState):
    optimized_op = _try_optimize_tm(operands, state.current_tm)

    try:
        # Always update state to the new absolute matrix
        state.current_tm = [float(x) for x in operands]
    except CONVERSION_ERRORS:
        state.current_tm = None

    if optimized_op:
        return optimized_op

    return (operands, operator)


def _handle_td(operands, operator, state: OptimizerState):
    if state.current_tm is not None:
        try:
            tx, ty = float(operands[0]), float(operands[1])
            a, b, c, d = (
                state.current_tm[0],
                state.current_tm[1],
                state.current_tm[2],
                state.current_tm[3],
            )
            # Update tracked matrix e/f
            state.current_tm[4] += (tx * a) + (ty * c)
            state.current_tm[5] += (tx * b) + (ty * d)
        except CONVERSION_ERRORS:
            state.current_tm = None
    return (operands, operator)


def _try_optimize_tm(operands, current_tm):
    """Attempts to convert an absolute Tm to a relative Td."""
    if current_tm is None:
        return None

    try:
        new_tm = [float(x) for x in operands]
        # Check if a, b, c, d match (scale/rotation/skew)
        matches_geometry = all(
            abs(new_tm[i] - current_tm[i]) < TM_TOL for i in range(4)
        )

        if matches_geometry:
            a, b, c, d = current_tm[0], current_tm[1], current_tm[2], current_tm[3]
            e_old, f_old = current_tm[4], current_tm[5]
            e_new, f_new = new_tm[4], new_tm[5]

            # Only optimize more-or-less diagonal matrices for safety
            if max(abs(b), abs(c)) < TM_TOL < min(abs(a), abs(d)):
                tx = (e_new - e_old) / a
                ty = (f_new - f_old) / d
                return (
                    [round(tx, ROUNDING_PLACES), round(ty, ROUNDING_PLACES)],
                    Operator("Td"),
                )
    except CONVERSION_ERRORS:
        pass

    return None

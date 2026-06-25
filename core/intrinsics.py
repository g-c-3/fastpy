"""
FastPy Hardware Intrinsics — Chess Pattern Mapper
==================================================
Recognises chess-specific Python expression patterns in the IR and replaces
them with single-clock-cycle CPU hardware instructions via GCC/Clang builtins.

Architecture
------------
The emitter calls IntrinsicMapper.try_intrinsic(node) before emitting any
expression. If the node matches a known pattern, try_intrinsic returns the
C++ string directly. Otherwise it returns None and the emitter falls back
to baseline C++.

The mapper receives a reference to the emitter's _emit_expr function so it
can recursively emit the arguments of matched patterns (e.g. the `board`
variable inside bin(board).count("1")).

Patterns Covered
----------------

  POPCNT — Population Count (count set bits)
  ┌─────────────────────────────────────────────────────────────────┐
  │ Python:   bin(board).count("1")                                 │
  │ C++:      __builtin_popcountll(board)                           │
  │ CPU:      POPCNT  (1 clock cycle, all modern x86-64 CPUs)       │
  │ Speedup:  ~50–200x vs Python string counting                    │
  └─────────────────────────────────────────────────────────────────┘

  TZCNT — Trailing Zero Count (index of least significant bit)
  ┌─────────────────────────────────────────────────────────────────┐
  │ Python:   (board & -board).bit_length() - 1                     │
  │ C++:      __builtin_ctzll(board)                                │
  │ CPU:      TZCNT / BSF  (1 clock cycle, Intel Haswell+)          │
  │ Speedup:  ~10–30x vs Python bit_length approach                 │
  └─────────────────────────────────────────────────────────────────┘

  BLSI — Isolate Lowest Set Bit  (BMI1)
  ┌─────────────────────────────────────────────────────────────────┐
  │ Python:   board & -board                                        │
  │ C++:      (board & -board)  [GCC auto-vectorises to BLSI]       │
  │ Note:     Already optimal in C++. No substitution needed.       │
  └─────────────────────────────────────────────────────────────────┘

  BLSR — Reset Lowest Set Bit  (BMI1)
  ┌─────────────────────────────────────────────────────────────────┐
  │ Python:   board & (board - 1)                                   │
  │ C++:      (board & (board - 1))  [GCC auto-vectorises to BLSR]  │
  │ Note:     Already optimal in C++. No substitution needed.       │
  └─────────────────────────────────────────────────────────────────┘

Adding New Patterns
-------------------
1. Add a _match_* method that returns str | None
2. Call it from the relevant dispatch block in try_intrinsic()
3. Add an entry to PATTERN_REGISTRY for documentation / testing

Author: Gokul Chandar
Project: FastPy (github.com/g-c-3/fastpy)
License: MIT
"""

from __future__ import annotations

from typing import Callable, Optional, Any

from .parser import (
    IRCall, IRBinOp, IRUnaryOp, IRLiteral, IRName,
)


# =============================================================================
# PATTERN REGISTRY
# Documents every recognised pattern for tooling, tests, and --list-intrinsics.
# =============================================================================

PATTERN_REGISTRY: list[dict] = [
    {
        "name":        "POPCNT",
        "python":      'bin(board).count("1")',
        "cpp":         "__builtin_popcountll(board)",
        "instruction": "POPCNT",
        "cycles":      1,
        "requires":    "SSE4.2 (Intel Nehalem 2008+ / AMD Barcelona 2007+)",
    },
    {
        "name":        "TZCNT",
        "python":      "(board & -board).bit_length() - 1",
        "cpp":         "__builtin_ctzll(board)",
        "instruction": "TZCNT / BSF",
        "cycles":      1,
        "requires":    "BMI1 (Intel Haswell 2013+ / AMD Piledriver 2012+)",
    },
]


# =============================================================================
# INTRINSIC MAPPER
# =============================================================================

class IntrinsicMapper:
    """
    Pattern-matches IR expression nodes and returns C++ hardware intrinsic
    strings in place of baseline C++ emission.

    Instantiated by emitter.emit_module() and injected as the intrinsic_hook.
    The emit_expr reference lets the mapper recursively emit subexpressions
    (e.g. to extract the `board` argument from bin(board).count("1")).
    """

    def __init__(self, emit_expr: Callable[[Any], str]) -> None:
        self._emit = emit_expr

    def try_intrinsic(self, node: Any) -> Optional[str]:
        """
        Entry point called by the emitter for every expression node.

        Returns a C++ string if the node matches a hardware intrinsic pattern.
        Returns None to let the emitter fall back to baseline C++.

        Designed to be fast: only IRCall and IRBinOp can match known patterns,
        so all other node types are rejected immediately.
        """
        t = type(node).__name__

        if t == "IRCall":
            return self._match_call(node)
        if t == "IRBinOp":
            return self._match_binop(node)

        return None   # All other node types: no intrinsic applies

    # =========================================================================
    # CALL PATTERNS
    # =========================================================================

    def _match_call(self, node: IRCall) -> Optional[str]:
        """Match call-expression intrinsic patterns."""

        # ── POPCNT ────────────────────────────────────────────────────────────
        # Pattern:  bin(x).count("1")
        # Matches:  IRCall(func="<expr>.count",
        #               args=[IRLiteral("1", "str")],
        #               receiver=IRCall(func="bin", args=[x]))
        result = self._match_popcnt(node)
        if result is not None:
            return result

        # ── TZCNT ─────────────────────────────────────────────────────────────
        # Pattern:  (x & -x).bit_length() - 1
        # The outer subtraction (-1) is an IRBinOp handled in _match_binop.
        # Here we match the inner call: (x & -x).bit_length()
        result = self._match_bit_length(node)
        if result is not None:
            return result

        return None

    def _match_popcnt(self, node: IRCall) -> Optional[str]:
        """
        bin(x).count("1")  →  __builtin_popcountll(x)

        Shape:
            IRCall(
                func     = "<expr>.count",
                args     = [IRLiteral(value="1", kind="str")],
                receiver = IRCall(func="bin", args=[<board_expr>])
            )
        """
        if node.func != "<expr>.count":
            return None
        if len(node.args) != 1:
            return None
        if not isinstance(node.args[0], IRLiteral):
            return None
        if node.args[0].value != "1":
            return None
        if node.receiver is None:
            return None
        if not isinstance(node.receiver, IRCall):
            return None
        if node.receiver.func != "bin":
            return None
        if len(node.receiver.args) != 1:
            return None

        board = self._emit(node.receiver.args[0])
        return f"__builtin_popcountll({board})"

    def _match_bit_length(self, node: IRCall) -> Optional[str]:
        """
        (x & -x).bit_length()  →  __builtin_ctzll(x) + 1

        This is the inner call of the full TZCNT pattern:
            (x & -x).bit_length() - 1  →  __builtin_ctzll(x)
        The outer `- 1` is matched in _match_tzcnt() in _match_binop.

        Shape:
            IRCall(
                func     = "<expr>.bit_length",
                args     = [],
                receiver = IRBinOp("&", x, IRUnaryOp("-", x))
            )
        where both x references are the same variable.
        """
        if node.func != "<expr>.bit_length":
            return None
        if len(node.args) != 0:
            return None
        if node.receiver is None:
            return None
        if not isinstance(node.receiver, IRBinOp):
            return None

        inner = node.receiver
        if inner.op != "&":
            return None
        if not isinstance(inner.right, IRUnaryOp):
            return None
        if inner.right.op != "-":
            return None

        left_str  = self._emit(inner.left)
        right_str = self._emit(inner.right.operand)
        if left_str != right_str:
            return None   # Not the same variable — not safe to replace

        # Emit ctzll + 1 because bit_length() is 1-indexed
        return f"(__builtin_ctzll({left_str}) + 1)"

    # =========================================================================
    # BINOP PATTERNS
    # =========================================================================

    def _match_binop(self, node: IRBinOp) -> Optional[str]:
        """Match binary-operation intrinsic patterns."""

        # ── TZCNT (full pattern) ──────────────────────────────────────────────
        # Pattern:  (x & -x).bit_length() - 1  →  __builtin_ctzll(x)
        result = self._match_tzcnt(node)
        if result is not None:
            return result

        return None

    def _match_tzcnt(self, node: IRBinOp) -> Optional[str]:
        """
        (x & -x).bit_length() - 1  →  __builtin_ctzll(x)

        Shape:
            IRBinOp(
                op    = "-",
                left  = IRCall(func="<expr>.bit_length",
                               receiver=IRBinOp("&", x, IRUnaryOp("-", x))),
                right = IRLiteral(value=1, kind="int")
            )

        The inner IRCall is already matched by _match_bit_length which emits
        `(__builtin_ctzll(x) + 1)`. Here we detect the `- 1` and collapse it:
            (__builtin_ctzll(x) + 1) - 1  →  __builtin_ctzll(x)
        """
        if node.op != "-":
            return None
        if not isinstance(node.right, IRLiteral):
            return None
        if node.right.value != 1:
            return None
        if not isinstance(node.left, IRCall):
            return None

        # Try to match the inner bit_length() call
        inner_result = self._match_bit_length(node.left)
        if inner_result is None:
            return None

        # inner_result is "(__builtin_ctzll(x) + 1)"
        # We are subtracting 1 → collapse to __builtin_ctzll(x)
        if inner_result.startswith("(__builtin_ctzll(") and \
                inner_result.endswith(") + 1)"):
            # Strip the outer parens and the + 1
            ctz_call = inner_result[1:-len(") + 1)")]  # → "__builtin_ctzll(x)"
            return ctz_call

        return None


# =============================================================================
# UTILITIES
# =============================================================================

def list_patterns() -> str:
    """
    Return a human-readable table of all registered intrinsic patterns.
    Used by `fastpy --list-intrinsics`.
    """
    lines = ["FastPy Hardware Intrinsics\n"]
    lines.append(f"{'Pattern':<40} {'Instruction':<10} {'Cycles'}")
    lines.append("-" * 60)
    for p in PATTERN_REGISTRY:
        lines.append(
            f"{p['python']:<40} {p['instruction']:<10} {p['cycles']} cycle"
        )
        lines.append(f"  → {p['cpp']}")
        lines.append(f"     Requires: {p['requires']}")
        lines.append("")
    return "\n".join(lines)

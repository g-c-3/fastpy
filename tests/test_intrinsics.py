"""
Tests for core/intrinsics.py
=============================
Covers: POPCNT pattern, TZCNT pattern, non-matching patterns,
        end-to-end pipeline firing, PATTERN_REGISTRY contents.
"""

import pytest
from core.parser      import parse_source, IRCall, IRBinOp, IRUnaryOp, IRName, IRLiteral
from core.type_system  import check_module
from core.emitter      import emit_module
from core.intrinsics   import IntrinsicMapper, PATTERN_REGISTRY
from conftest import TYPE_ALIASES, emit_from_source, POPCOUNT_SOURCE, TZCNT_SOURCE


# =============================================================================
# PATTERN REGISTRY
# =============================================================================

class TestPatternRegistry:

    def test_registry_is_not_empty(self):
        assert len(PATTERN_REGISTRY) > 0

    def test_popcnt_registered(self):
        names = [p["name"] for p in PATTERN_REGISTRY]
        assert "POPCNT" in names

    def test_tzcnt_registered(self):
        names = [p["name"] for p in PATTERN_REGISTRY]
        assert "TZCNT" in names

    def test_each_entry_has_required_keys(self):
        required = {"name", "python", "cpp", "instruction", "cycles"}
        for pattern in PATTERN_REGISTRY:
            assert required.issubset(pattern.keys()), \
                f"Pattern {pattern.get('name')} missing keys"


# =============================================================================
# POPCNT — bin(x).count("1") → __builtin_popcountll(x)
# =============================================================================

class TestPopcntPattern:

    def test_popcnt_fires_in_pipeline(self):
        cpp = emit_from_source(POPCOUNT_SOURCE)
        assert "__builtin_popcountll(board)" in cpp

    def test_python_string_counting_not_in_output(self):
        cpp = emit_from_source(POPCOUNT_SOURCE)
        assert 'bin(board).count' not in cpp

    def test_popcnt_with_named_variable(self):
        src = TYPE_ALIASES + "def count_pawns(pawns: uint64) -> int32:\n    return bin(pawns).count(\"1\")"
        cpp = emit_from_source(src)
        assert "__builtin_popcountll(pawns)" in cpp

    def test_popcnt_inside_expression(self):
        """POPCNT should fire even when the result is part of a larger expression."""
        src = (
            TYPE_ALIASES
            + "def f(a: uint64, b: uint64) -> int32:\n"
            + '    return bin(a).count("1") + bin(b).count("1")'
        )
        cpp = emit_from_source(src)
        assert cpp.count("__builtin_popcountll") == 2

    def test_popcnt_mapper_directly(self):
        """Unit-test the mapper in isolation using a manually constructed IR node."""
        # Build: bin(board).count("1")
        board    = IRName(name="board")
        bin_call = IRCall(func="bin", args=[board])
        one      = IRLiteral(value="1", kind="str")
        node     = IRCall(func="<expr>.count", args=[one], receiver=bin_call)

        mapper = IntrinsicMapper(emit_expr=lambda n: n.name if isinstance(n, IRName) else "")
        result = mapper.try_intrinsic(node)
        assert result == "__builtin_popcountll(board)"

    def test_popcnt_wrong_arg_not_matched(self):
        """count("0") must NOT trigger POPCNT."""
        board    = IRName(name="board")
        bin_call = IRCall(func="bin", args=[board])
        zero     = IRLiteral(value="0", kind="str")
        node     = IRCall(func="<expr>.count", args=[zero], receiver=bin_call)

        mapper = IntrinsicMapper(emit_expr=lambda n: n.name if isinstance(n, IRName) else "")
        result = mapper.try_intrinsic(node)
        assert result is None

    def test_popcnt_no_receiver_not_matched(self):
        """count("1") with no receiver must NOT trigger POPCNT."""
        one  = IRLiteral(value="1", kind="str")
        node = IRCall(func="<expr>.count", args=[one], receiver=None)

        mapper = IntrinsicMapper(emit_expr=lambda n: "")
        result = mapper.try_intrinsic(node)
        assert result is None


# =============================================================================
# TZCNT — (x & -x).bit_length() - 1 → __builtin_ctzll(x)
# =============================================================================

class TestTzcntPattern:

    def test_tzcnt_fires_in_pipeline(self):
        cpp = emit_from_source(TZCNT_SOURCE)
        assert "__builtin_ctzll(board)" in cpp

    def test_python_bit_length_not_in_output(self):
        cpp = emit_from_source(TZCNT_SOURCE)
        assert "bit_length" not in cpp

    def test_tzcnt_with_named_variable(self):
        src = TYPE_ALIASES + "def f(knights: uint64) -> int32:\n    return (knights & -knights).bit_length() - 1"
        cpp = emit_from_source(src)
        assert "__builtin_ctzll(knights)" in cpp

    def test_tzcnt_wrong_subtracted_value_not_matched(self):
        """(x & -x).bit_length() - 2 must NOT trigger TZCNT."""
        src = TYPE_ALIASES + "def f(x: uint64) -> int32:\n    return (x & -x).bit_length() - 2"
        cpp = emit_from_source(src)
        assert "__builtin_ctzll" not in cpp

    def test_tzcnt_different_variables_not_matched(self):
        """(x & -y).bit_length() - 1 — different variables — must NOT trigger."""
        src = TYPE_ALIASES + "def f(x: uint64, y: uint64) -> int32:\n    return (x & -y).bit_length() - 1"
        cpp = emit_from_source(src)
        assert "__builtin_ctzll" not in cpp


# =============================================================================
# NON-MATCHING PATTERNS
# =============================================================================

class TestNoMatch:

    def _mapper(self):
        return IntrinsicMapper(emit_expr=lambda n: "x")

    def test_name_node_returns_none(self):
        node   = IRName(name="board")
        result = self._mapper().try_intrinsic(node)
        assert result is None

    def test_literal_node_returns_none(self):
        node   = IRLiteral(value=42, kind="int")
        result = self._mapper().try_intrinsic(node)
        assert result is None

    def test_unrelated_binop_returns_none(self):
        node   = IRBinOp(left=IRName("x"), op="+", right=IRName("y"))
        result = self._mapper().try_intrinsic(node)
        assert result is None

    def test_unrelated_call_returns_none(self):
        node   = IRCall(func="popcount", args=[IRName("board")])
        result = self._mapper().try_intrinsic(node)
        assert result is None


# =============================================================================
# END-TO-END: SIMPLE ENGINE
# =============================================================================

class TestSimpleEngine:

    def test_simple_engine_emits_popcnt(self):
        """simple_engine.py must contain at least one POPCNT intrinsic."""
        import os
        from core.parser import parse_file
        engine_path = os.path.join(
            os.path.dirname(__file__), "..", "examples", "simple_engine.py"
        )
        ir     = parse_file(engine_path)
        result = check_module(ir)
        cpp    = emit_module(ir, result.registry)
        assert "__builtin_popcountll" in cpp

    def test_simple_engine_no_bin_count_in_output(self):
        """bin(x).count("1") must not appear anywhere in the emitted C++."""
        import os
        from core.parser import parse_file
        engine_path = os.path.join(
            os.path.dirname(__file__), "..", "examples", "simple_engine.py"
        )
        ir     = parse_file(engine_path)
        result = check_module(ir)
        cpp    = emit_module(ir, result.registry)
        assert 'bin(' not in cpp

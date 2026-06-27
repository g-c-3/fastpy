"""
Tests for core/emitter.py
==========================
Covers: constants, structs, functions, all statement types,
        expression emission, operator precedence, self. stripping.
"""

import pytest
from conftest import emit_from_source, TYPE_ALIASES


# =============================================================================
# FILE HEADER
# =============================================================================

class TestFileHeader:

    def test_header_comment_present(self):
        cpp = emit_from_source(TYPE_ALIASES)
        assert "FastPy-generated C++" in cpp

    def test_includes_cstdint(self):
        cpp = emit_from_source(TYPE_ALIASES)
        assert "#include <cstdint>" in cpp

    def test_includes_climits(self):
        cpp = emit_from_source(TYPE_ALIASES)
        assert "#include <climits>" in cpp


# =============================================================================
# CONSTANTS
# =============================================================================

class TestConstants:

    def test_constexpr_keyword(self):
        src = "from typing import Final\nuint64 = int\nFILE_A: Final[uint64] = 0x0101010101010101"
        cpp = emit_from_source(src)
        assert "constexpr" in cpp

    def test_uint64_constant_has_ull_suffix(self):
        src = "from typing import Final\nuint64 = int\nFILE_A: Final[uint64] = 0x0101010101010101"
        cpp = emit_from_source(src)
        assert "ULL" in cpp

    def test_small_uint64_has_ull_suffix(self):
        src = "from typing import Final\nuint64 = int\nRANK_1: Final[uint64] = 0xFF"
        cpp = emit_from_source(src)
        assert "ULL" in cpp

    def test_int32_constant_no_ull_suffix(self):
        src = "from typing import Final\nint32 = int\nMAX_DEPTH: Final[int32] = 64"
        cpp = emit_from_source(src)
        assert "64;" in cpp
        assert "ULL" not in cpp

    def test_constant_correct_type(self):
        src = "from typing import Final\nint32 = int\nMAX_DEPTH: Final[int32] = 64"
        cpp = emit_from_source(src)
        assert "int32_t MAX_DEPTH" in cpp


# =============================================================================
# STRUCT EMISSION
# =============================================================================

class TestStructEmission:

    BASE = (
        TYPE_ALIASES
        + "class Board:\n"
        + "    def __init__(self):\n"
        + "        self.pawns: uint64 = 0\n"
        + "        self.score: int32 = 0\n"
    )

    def test_struct_keyword(self):
        cpp = emit_from_source(self.BASE)
        assert "struct Board {" in cpp

    def test_struct_closing_brace(self):
        cpp = emit_from_source(self.BASE)
        assert "};  // struct Board" in cpp

    def test_field_types_emitted(self):
        cpp = emit_from_source(self.BASE)
        assert "uint64_t pawns" in cpp
        assert "int32_t score" in cpp

    def test_field_default_values(self):
        cpp = emit_from_source(self.BASE)
        assert "pawns = 0" in cpp

    def test_method_has_const_suffix(self):
        src = (
            self.BASE
            + "    def get_pawns(self) -> uint64:\n"
            + "        return self.pawns\n"
        )
        cpp = emit_from_source(src)
        assert "uint64_t get_pawns() const" in cpp

    def test_self_stripped_in_method(self):
        src = (
            self.BASE
            + "    def get_pawns(self) -> uint64:\n"
            + "        return self.pawns\n"
        )
        cpp = emit_from_source(src)
        assert "return pawns;" in cpp
        assert "self.pawns" not in cpp

    def test_forward_declaration_emitted(self):
        cpp = emit_from_source(self.BASE)
        assert "struct Board;" in cpp


# =============================================================================
# FUNCTION EMISSION
# =============================================================================

class TestFunctionEmission:

    def test_function_signature(self):
        src = TYPE_ALIASES + "def identity(x: int32) -> int32:\n    return x"
        cpp = emit_from_source(src)
        assert "int32_t identity(int32_t x)" in cpp

    def test_function_return(self):
        src = TYPE_ALIASES + "def identity(x: int32) -> int32:\n    return x"
        cpp = emit_from_source(src)
        assert "return x;" in cpp

    def test_void_return_type(self):
        src = TYPE_ALIASES + "def reset(x: int32) -> None:\n    return"
        cpp = emit_from_source(src)
        assert "void reset(" in cpp

    def test_multi_param_function(self):
        src = TYPE_ALIASES + "def add(a: int32, b: int32) -> int32:\n    return a"
        cpp = emit_from_source(src)
        assert "int32_t a" in cpp
        assert "int32_t b" in cpp


# =============================================================================
# STATEMENT EMISSION
# =============================================================================

class TestStatementEmission:

    def test_typed_declaration(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    y: int32 = 0\n    return y"
        cpp = emit_from_source(src)
        assert "int32_t y = 0;" in cpp

    def test_array_declaration(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    moves: uint64[218]\n    return x"
        cpp = emit_from_source(src)
        assert "uint64_t moves[218]" in cpp

    def test_aug_assign_plus(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    x += 1\n    return x"
        cpp = emit_from_source(src)
        assert "x += 1;" in cpp

    def test_aug_assign_bitand(self):
        src = TYPE_ALIASES + "def f(x: uint64, m: uint64) -> uint64:\n    x &= m\n    return x"
        cpp = emit_from_source(src)
        assert "x &= m;" in cpp

    def test_if_statement(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    if x > 0:\n        return 1\n    return 0"
        cpp = emit_from_source(src)
        assert "if (x > 0) {" in cpp

    def test_if_else_chain(self):
        src = (
            TYPE_ALIASES
            + "def f(x: int32) -> int32:\n"
            + "    if x > 0:\n        return 1\n"
            + "    else:\n        return 0"
        )
        cpp = emit_from_source(src)
        assert "} else {" in cpp

    def test_elif_chain(self):
        src = (
            TYPE_ALIASES
            + "def f(x: int32) -> int32:\n"
            + "    if x > 0:\n        return 1\n"
            + "    elif x < 0:\n        return -1\n"
            + "    else:\n        return 0"
        )
        cpp = emit_from_source(src)
        assert "} else if (x < 0) {" in cpp

    def test_while_loop(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    while x > 0:\n        x = 0\n    return x"
        cpp = emit_from_source(src)
        assert "while (x > 0) {" in cpp

    def test_for_range_one_arg(self):
        src = TYPE_ALIASES + "def f(n: int32) -> int32:\n    for i in range(n):\n        return i\n    return 0"
        cpp = emit_from_source(src)
        assert "for (int32_t i = 0; i < n; i++)" in cpp

    def test_for_range_two_args(self):
        src = TYPE_ALIASES + "def f(n: int32) -> int32:\n    for i in range(1, n):\n        return i\n    return 0"
        cpp = emit_from_source(src)
        assert "for (int32_t i = 1; i < n; i++)" in cpp

    def test_break_statement(self):
        src = TYPE_ALIASES + "def f(n: int32) -> int32:\n    for i in range(n):\n        break\n    return 0"
        cpp = emit_from_source(src)
        assert "break;" in cpp


# =============================================================================
# EXPRESSION EMISSION
# =============================================================================

class TestExpressionEmission:

    def _emit_return_expr(self, expr: str, extra_params: str = "") -> str:
        params = "x: uint64, y: uint64" + (", " + extra_params if extra_params else "")
        src = TYPE_ALIASES + f"def f({params}) -> uint64:\n    return {expr}"
        return emit_from_source(src)

    def test_bitwise_or_has_parens(self):
        cpp = self._emit_return_expr("x | y")
        assert "(x | (y))" in cpp

    def test_bitwise_and_has_parens(self):
        cpp = self._emit_return_expr("x & y")
        assert "(x & (y))" in cpp

    def test_bitwise_xor_has_parens(self):
        cpp = self._emit_return_expr("x ^ y")
        assert "(x ^ (y))" in cpp

    def test_left_shift_has_parens(self):
        cpp = self._emit_return_expr("x << 8")
        assert "(x << (8))" in cpp

    def test_right_shift_has_parens(self):
        cpp = self._emit_return_expr("x >> 1")
        assert "(x >> (1))" in cpp

    def test_addition_no_parens(self):
        cpp = self._emit_return_expr("x + y")
        assert "x + y" in cpp

    def test_not_operator(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    return not x"
        cpp = emit_from_source(src)
        assert "!x" in cpp

    def test_invert_operator(self):
        cpp = self._emit_return_expr("~x")
        assert "~x" in cpp

    def test_bool_and(self):
        src = TYPE_ALIASES + "def f(x: int32, y: int32) -> int32:\n    return x and y"
        cpp = emit_from_source(src)
        assert "&&" in cpp

    def test_bool_or(self):
        src = TYPE_ALIASES + "def f(x: int32, y: int32) -> int32:\n    return x or y"
        cpp = emit_from_source(src)
        assert "||" in cpp

    def test_true_literal(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    return True"
        cpp = emit_from_source(src)
        assert "return true;" in cpp

    def test_false_literal(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    return False"
        cpp = emit_from_source(src)
        assert "return false;" in cpp

    def test_ternary_expression(self):
        cpp = self._emit_return_expr("x if x > y else y")
        assert "?" in cpp
        assert ":" in cpp


class TestArrayParamDecay:

    def _check(self, src):
        from core.parser import parse_source
        from core.type_system import check_module
        from core.emitter import emit_module
        ir = parse_source(src)
        result = check_module(ir)
        return emit_module(ir, result.registry)

    def test_array_param_decays_to_pointer(self):
        src = (
            "uint64 = int\nint32 = int\n"
            "def fill(moves: uint64[218], count: int32) -> int32:\n"
            "    return count\n"
        )
        cpp = self._check(src)
        assert "uint64_t* moves" in cpp

    def test_array_local_stays_stack(self):
        src = (
            "uint64 = int\nint32 = int\n"
            "def f(count: int32) -> int32:\n"
            "    moves: uint64[218]\n"
            "    return count\n"
        )
        cpp = self._check(src)
        assert "uint64_t moves[218]" in cpp

    def test_subscript_write_emits_assignment(self):
        src = (
            "uint64 = int\nint32 = int\n"
            "def fill(moves: uint64[218], count: int32) -> int32:\n"
            "    moves[count] = 42\n"
            "    return count\n"
        )
        cpp = self._check(src)
        assert "moves[count] = 42" in cpp


class TestVariableHoisting:

    def _emit(self, src):
        from core.parser import parse_source
        from core.type_system import check_module
        from core.emitter import emit_module
        ir = parse_source(src)
        result = check_module(ir)
        return emit_module(ir, result.registry)

    def test_var_declared_in_while_accessible_in_sibling_while(self):
        """
        Python flat scope: a variable declared inside one while block
        must be accessible in a sibling while block.
        The emitter achieves this by hoisting all scalars to function top.
        """
        src = (
            "uint64 = int\nint32 = int\n"
            "def f(a: int32, b: int32) -> int32:\n"
            "    while a:\n"
            "        x: int32 = a\n"
            "        a -= 1\n"
            "    while b:\n"
            "        x = b\n"   # x not declared here but must be in scope
            "        b -= 1\n"
            "    return x\n"
        )
        cpp = self._emit(src)
        fn_lines = cpp[cpp.index("int32_t f("):]
        # x must be declared before the first while, not inside it
        x_decl_pos   = fn_lines.index("int32_t x = 0")
        first_while   = fn_lines.index("while (a)")
        assert x_decl_pos < first_while, "x should be hoisted above first while"

    def test_hoisted_uint64_gets_ull_zero(self):
        src = (
            "uint64 = int\nint32 = int\n"
            "def f(a: uint64) -> uint64:\n"
            "    while a:\n"
            "        temp: uint64 = a\n"
            "        a = 0\n"
            "    return temp\n"
        )
        cpp = self._emit(src)
        assert "uint64_t temp = 0ULL" in cpp

    def test_hoisted_bool_gets_false_zero(self):
        src = (
            "bool8 = bool\nint32 = int\n"
            "def f(a: int32) -> bool8:\n"
            "    while a:\n"
            "        found: bool8 = True\n"
            "        a -= 1\n"
            "    return found\n"
        )
        cpp = self._emit(src)
        assert "bool found = false" in cpp

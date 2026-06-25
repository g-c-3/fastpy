"""
Tests for core/parser.py
=========================
Covers: type aliases, constants, functions, classes,
        all expression types, all statement types, error cases.
"""

import pytest
from core.parser import (
    parse_source, FastPyParseError,
    IRTypeAlias, IRConstant, IRFunction, IRClass, IRField, IRParam,
    IRAssign, IRAugAssign, IRReturn, IRIf, IRWhile, IRFor, IRBreak,
    IRName, IRLiteral, IRBinOp, IRUnaryOp, IRCompare, IRBoolOp,
    IRCall, IRAttribute, IRSubscript, IRIfExp,
)
from conftest import TYPE_ALIASES


# =============================================================================
# TYPE ALIASES
# =============================================================================

class TestTypeAliases:

    def test_uint64_alias_name(self):
        ir = parse_source("uint64 = int")
        assert ir.type_aliases[0].name == "uint64"

    def test_uint64_alias_cpp_type(self):
        ir = parse_source("uint64 = int")
        assert ir.type_aliases[0].cpp_type == "uint64_t"

    def test_int32_alias(self):
        ir = parse_source("int32 = int")
        assert ir.type_aliases[0].cpp_type == "int32_t"

    def test_bool8_alias(self):
        ir = parse_source("bool8 = bool")
        assert ir.type_aliases[0].cpp_type == "bool"

    def test_all_three_aliases_parsed(self):
        ir = parse_source(TYPE_ALIASES)
        names = [a.name for a in ir.type_aliases]
        assert "uint64" in names
        assert "int32"  in names
        assert "bool8"  in names

    def test_non_type_assignment_ignored(self):
        ir = parse_source("MAX_DEPTH = 10")
        assert len(ir.type_aliases) == 0


# =============================================================================
# CONSTANTS
# =============================================================================

class TestConstants:

    def test_constant_name(self):
        src = "from typing import Final\nuint64 = int\nFILE_A: Final[uint64] = 0x0101010101010101"
        ir = parse_source(src)
        assert ir.constants[0].name == "FILE_A"

    def test_constant_type_name(self):
        src = "from typing import Final\nuint64 = int\nFILE_A: Final[uint64] = 0x0101010101010101"
        ir = parse_source(src)
        assert ir.constants[0].type_name == "uint64"

    def test_constant_value_is_literal(self):
        src = "from typing import Final\nuint64 = int\nFILE_A: Final[uint64] = 0x01"
        ir  = parse_source(src)
        assert isinstance(ir.constants[0].value, IRLiteral)
        assert ir.constants[0].value.kind == "int"

    def test_non_final_annotation_not_a_constant(self):
        src = "uint64 = int\nboard: uint64 = 0"
        ir  = parse_source(src)
        assert len(ir.constants) == 0

    def test_negative_constant(self):
        src = "from typing import Final\nint32 = int\nNEG_INF: Final[int32] = -32767"
        ir  = parse_source(src)
        val = ir.constants[0].value
        assert isinstance(val, IRUnaryOp)
        assert val.op == "-"


# =============================================================================
# FUNCTIONS
# =============================================================================

class TestFunctions:

    def test_function_name(self):
        ir = parse_source(TYPE_ALIASES + "def foo(x: int32) -> int32:\n    return x")
        assert ir.functions[0].name == "foo"

    def test_function_param_name_and_type(self):
        ir = parse_source(TYPE_ALIASES + "def foo(board: uint64) -> int32:\n    return 0")
        param = ir.functions[0].params[0]
        assert param.name == "board"
        assert param.type_name == "uint64"

    def test_function_return_type(self):
        ir = parse_source(TYPE_ALIASES + "def foo(x: int32) -> uint64:\n    return 0")
        assert ir.functions[0].return_type == "uint64"

    def test_function_no_params(self):
        ir = parse_source(TYPE_ALIASES + "def foo() -> int32:\n    return 0")
        assert ir.functions[0].params == []

    def test_function_body_has_return(self):
        ir = parse_source(TYPE_ALIASES + "def foo(x: int32) -> int32:\n    return x")
        body = ir.functions[0].body
        assert len(body) == 1
        assert isinstance(body[0], IRReturn)

    def test_function_docstring_skipped(self):
        src = TYPE_ALIASES + 'def foo(x: int32) -> int32:\n    """Docstring."""\n    return x'
        ir  = parse_source(src)
        body = ir.functions[0].body
        # Docstring must not appear as a statement
        assert len(body) == 1
        assert isinstance(body[0], IRReturn)

    def test_multiple_functions(self):
        src = TYPE_ALIASES + "def foo(x: int32) -> int32:\n    return x\ndef bar(y: int32) -> int32:\n    return y"
        ir  = parse_source(src)
        assert len(ir.functions) == 2


# =============================================================================
# CLASSES
# =============================================================================

class TestClasses:

    def test_class_name(self):
        src = TYPE_ALIASES + "class Board:\n    def __init__(self):\n        self.pawns: uint64 = 0"
        ir  = parse_source(src)
        assert ir.classes[0].name == "Board"

    def test_class_field_name_and_type(self):
        src = TYPE_ALIASES + "class Board:\n    def __init__(self):\n        self.pawns: uint64 = 0"
        ir  = parse_source(src)
        field = ir.classes[0].fields[0]
        assert field.name == "pawns"
        assert field.type_name == "uint64"

    def test_class_field_default_value(self):
        src = TYPE_ALIASES + "class Board:\n    def __init__(self):\n        self.pawns: uint64 = 0"
        ir  = parse_source(src)
        assert isinstance(ir.classes[0].fields[0].default_value, IRLiteral)

    def test_class_method_parsed(self):
        src = (
            TYPE_ALIASES
            + "class Board:\n"
            + "    def __init__(self):\n"
            + "        self.pawns: uint64 = 0\n"
            + "    def count(self) -> int32:\n"
            + "        return 0\n"
        )
        ir = parse_source(src)
        assert len(ir.classes[0].methods) == 1
        assert ir.classes[0].methods[0].name == "count"

    def test_class_method_is_method_flag(self):
        src = (
            TYPE_ALIASES
            + "class Board:\n"
            + "    def __init__(self):\n"
            + "        self.x: int32 = 0\n"
            + "    def get(self) -> int32:\n"
            + "        return self.x\n"
        )
        ir = parse_source(src)
        assert ir.classes[0].methods[0].is_method is True


# =============================================================================
# EXPRESSIONS
# =============================================================================

class TestExpressions:

    def _expr(self, expr_src: str):
        """Parse a single expression from a return statement."""
        src = TYPE_ALIASES + f"def f(x: uint64, y: uint64) -> uint64:\n    return {expr_src}"
        ir  = parse_source(src)
        return ir.functions[0].body[0].value

    def test_integer_literal(self):
        node = self._expr("0")
        assert isinstance(node, IRLiteral)
        assert node.kind == "int"
        assert node.value == 0

    def test_hex_literal(self):
        node = self._expr("0xFF")
        assert isinstance(node, IRLiteral)
        assert node.value == 255

    def test_bool_literal_true(self):
        node = self._expr("True")
        assert isinstance(node, IRLiteral)
        assert node.kind == "bool"
        assert node.value is True

    def test_name_reference(self):
        node = self._expr("x")
        assert isinstance(node, IRName)
        assert node.name == "x"

    def test_binop_or(self):
        node = self._expr("x | y")
        assert isinstance(node, IRBinOp)
        assert node.op == "|"

    def test_binop_and(self):
        node = self._expr("x & y")
        assert isinstance(node, IRBinOp)
        assert node.op == "&"

    def test_binop_lshift(self):
        node = self._expr("x << 8")
        assert isinstance(node, IRBinOp)
        assert node.op == "<<"
        assert isinstance(node.right, IRLiteral)
        assert node.right.value == 8

    def test_unary_invert(self):
        node = self._expr("~x")
        assert isinstance(node, IRUnaryOp)
        assert node.op == "~"

    def test_unary_negate(self):
        node = self._expr("-x")
        assert isinstance(node, IRUnaryOp)
        assert node.op == "-"

    def test_compare_eq(self):
        node = self._expr("x == y")
        assert isinstance(node, IRCompare)
        assert node.op == "=="

    def test_compare_gt(self):
        node = self._expr("x > y")
        assert isinstance(node, IRCompare)
        assert node.op == ">"

    def test_boolop_and(self):
        node = self._expr("x and y")
        assert isinstance(node, IRBoolOp)
        assert node.op == "and"

    def test_function_call(self):
        node = self._expr("popcount(x)")
        assert isinstance(node, IRCall)
        assert node.func == "popcount"
        assert len(node.args) == 1

    def test_method_call_on_name(self):
        node = self._expr("x.bit_length()")
        assert isinstance(node, IRCall)
        assert node.func == "x.bit_length"

    def test_method_call_receiver_preserved(self):
        """bin(x).count("1") must preserve bin(x) as the receiver."""
        node = self._expr('bin(x).count("1")')
        assert isinstance(node, IRCall)
        assert node.func == "<expr>.count"
        assert isinstance(node.receiver, IRCall)
        assert node.receiver.func == "bin"

    def test_subscript(self):
        src = TYPE_ALIASES + "def f(moves: uint64, i: int32) -> uint64:\n    return moves[i]"
        ir  = parse_source(src)
        node = ir.functions[0].body[0].value
        assert isinstance(node, IRSubscript)

    def test_ternary(self):
        node = self._expr("x if x > y else y")
        assert isinstance(node, IRIfExp)


# =============================================================================
# STATEMENTS
# =============================================================================

class TestStatements:

    def _body(self, stmts_src: str):
        """Parse a function body and return the statement list."""
        src = TYPE_ALIASES + f"def f(x: int32, y: int32) -> int32:\n{stmts_src}\n    return 0"
        ir  = parse_source(src)
        return ir.functions[0].body

    def test_annotated_assign(self):
        body = self._body("    score: int32 = 0")
        assert isinstance(body[0], IRAssign)
        assert body[0].target == "score"
        assert body[0].type_name == "int32"

    def test_plain_assign(self):
        body = self._body("    score: int32 = 0\n    score = 1")
        assert isinstance(body[1], IRAssign)
        assert body[1].type_name is None

    def test_aug_assign(self):
        body = self._body("    x: int32 = 0\n    x += 1")
        assert isinstance(body[1], IRAugAssign)
        assert body[1].op == "+"

    def test_if_statement(self):
        body = self._body("    if x > 0:\n        return 1")
        assert isinstance(body[0], IRIf)

    def test_if_else(self):
        body = self._body("    if x > 0:\n        return 1\n    else:\n        return 0")
        stmt = body[0]
        assert isinstance(stmt, IRIf)
        assert len(stmt.orelse) > 0

    def test_while_loop(self):
        body = self._body("    x: int32 = 1\n    while x > 0:\n        x = 0")
        assert isinstance(body[1], IRWhile)

    def test_for_loop(self):
        body = self._body("    for i in range(8):\n        return 0")
        assert isinstance(body[0], IRFor)
        assert body[0].target == "i"

    def test_break_statement(self):
        body = self._body("    for i in range(8):\n        break")
        for_body = body[0].body
        assert isinstance(for_body[0], IRBreak)


# =============================================================================
# ERROR CASES
# =============================================================================

class TestParseErrors:

    def test_unsupported_expression_raises(self):
        # Lambda is not part of the FastPy dialect
        with pytest.raises(FastPyParseError):
            parse_source(TYPE_ALIASES + "def f(x: int32) -> int32:\n    return (lambda: 0)()")

    def test_non_empty_list_literal_raises(self):
        with pytest.raises(FastPyParseError):
            parse_source(TYPE_ALIASES + "def f(x: int32) -> int32:\n    return [1, 2, 3]")

    def test_syntax_error_raises(self):
        with pytest.raises(SyntaxError):
            parse_source("def f(: :")

    def test_imports_are_silently_skipped(self):
        ir = parse_source("import sys\nfrom typing import Final\nuint64 = int")
        assert len(ir.functions) == 0
        assert len(ir.type_aliases) == 1

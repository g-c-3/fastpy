"""
FastPy Parser — AST Structural Visitor
=======================================
Reads Python source code using Python's built-in `ast` module.
Produces a FastPy Intermediate Representation (IR) — a clean tree
of dataclasses that the type_system, emitter, and intrinsics modules
can all operate on.

The parser does NOT:
  - Validate types          (type_system.py)
  - Generate C++            (emitter.py)
  - Map hardware intrinsics (intrinsics.py)

The parser's only job:
  Python source → FastPy IR

Author: Gokul Chandar
Project: FastPy (github.com/g-c-3/fastpy)
License: MIT
"""

import ast
from dataclasses import dataclass, field
from typing import Optional, Any


# =============================================================================
# BUILTIN TYPE MAP
# FastPy dialect type names → C++ equivalents.
# Expanded at runtime as the parser discovers new type alias declarations.
# =============================================================================

BUILTIN_TYPE_MAP: dict[str, str] = {
    "uint64": "uint64_t",
    "int32":  "int32_t",
    "bool8":  "bool",
    "int":    "int32_t",
    "bool":   "bool",
    "None":   "void",
}


# =============================================================================
# IR NODE DEFINITIONS
# Every FastPy dialect construct maps to exactly one of these nodes.
# =============================================================================

# --- Type-level nodes --------------------------------------------------------

@dataclass
class IRTypeAlias:
    """A top-level type alias: `uint64 = int` → C++ uint64_t."""
    name: str
    cpp_type: str


@dataclass
class IRConstant:
    """A Final-annotated module-level constant: `FILE_A: Final[uint64] = 0x01...`"""
    name: str
    type_name: str
    value: Any


@dataclass
class IRParam:
    """A single function parameter with its type annotation."""
    name: str
    type_name: str


# --- Expression nodes --------------------------------------------------------

@dataclass
class IRName:
    """A variable or constant reference: `board`, `FILE_A`"""
    name: str


@dataclass
class IRLiteral:
    """A numeric or boolean literal: `0xFF`, `True`, `-32767`"""
    value: Any
    kind: str   # "int" | "bool" | "none" | "empty_list"


@dataclass
class IRBinOp:
    """A binary operation: `board << 8`, `alpha & beta`"""
    left: Any
    op: str     # "+", "-", "*", "/", "//", "%", "<<", ">>", "|", "&", "^"
    right: Any


@dataclass
class IRUnaryOp:
    """A unary operation: `~board`, `-x`, `not flag`"""
    op: str     # "~", "-", "not", "+"
    operand: Any


@dataclass
class IRCompare:
    """A comparison: `depth == 0`, `alpha >= beta`"""
    left: Any
    op: str     # "==", "!=", "<", ">", "<=", ">="
    right: Any


@dataclass
class IRBoolOp:
    """A boolean operation: `x and y`, `a or b`"""
    op: str     # "and" | "or"
    values: list


@dataclass
class IRCall:
    """
    A function or method call: `popcount(board)`, `self.white_pieces()`
    func is a flat string: "popcount", "self.make_move"

    receiver holds the object expression for method calls on non-name objects.
    e.g. bin(board).count("1") → func="<expr>.count", receiver=IRCall("bin",[board])
    This lets intrinsics.py pattern-match the full call chain.
    """
    func: str
    args: list
    receiver: Any = None


@dataclass
class IRAttribute:
    """An attribute access: `board.white_pawns`, `self.castling_rights`"""
    obj: Any
    attr: str


@dataclass
class IRSubscript:
    """A subscript: `moves[i]`"""
    obj: Any
    index: Any


@dataclass
class IRTuple:
    """A tuple literal: `(from_sq, to_sq)`"""
    elements: list


@dataclass
class IRIfExp:
    """A ternary expression: `a if condition else b`"""
    condition: Any
    body: Any
    orelse: Any


# --- Statement nodes ---------------------------------------------------------

@dataclass
class IRAssign:
    """
    An assignment, with or without a type annotation.
      `x: int32 = 0`     → type_name="int32"
      `best = NEG_INF`   → type_name=None
    """
    target: str
    value: Any
    type_name: Optional[str] = None


@dataclass
class IRAugAssign:
    """An augmented assignment: `alpha += score`, `board &= mask`"""
    target: str
    op: str
    value: Any


@dataclass
class IRReturn:
    """A return statement: `return best`"""
    value: Any


@dataclass
class IRIf:
    """An if / elif / else block."""
    condition: Any
    body: list
    orelse: list    # empty [] if no else; [IRIf(...)] for elif


@dataclass
class IRWhile:
    """A while loop: `while temp:`"""
    condition: Any
    body: list


@dataclass
class IRFor:
    """A for loop: `for i in range(n):`"""
    target: str
    iterable: Any
    body: list


@dataclass
class IRBreak:
    """A break statement."""
    pass


@dataclass
class IRExprStatement:
    """An expression used as a statement — typically a call for its side effects."""
    expr: Any


# --- Top-level structure nodes -----------------------------------------------

@dataclass
class IRField:
    """A typed class field declared in __init__."""
    name: str
    type_name: str
    default_value: Any


@dataclass
class IRFunction:
    """A complete function definition."""
    name: str
    params: list            # list[IRParam]
    return_type: str
    body: list              # list of IR statement nodes
    is_method: bool = False


@dataclass
class IRClass:
    """A class definition — compiled to a C++ struct."""
    name: str
    fields: list            # list[IRField]  — from __init__
    methods: list           # list[IRFunction]


@dataclass
class IRModule:
    """The top-level IR node for an entire FastPy source file."""
    source_file: str
    type_aliases: list      # list[IRTypeAlias]
    constants: list         # list[IRConstant]
    functions: list         # list[IRFunction]
    classes: list           # list[IRClass]


# =============================================================================
# OPERATOR MAPS
# Translate Python AST operator nodes → string tokens the emitter can use.
# =============================================================================

BIN_OP_MAP: dict[type, str] = {
    ast.Add:      "+",
    ast.Sub:      "-",
    ast.Mult:     "*",
    ast.Div:      "/",
    ast.FloorDiv: "//",
    ast.Mod:      "%",
    ast.LShift:   "<<",
    ast.RShift:   ">>",
    ast.BitOr:    "|",
    ast.BitAnd:   "&",
    ast.BitXor:   "^",
}

UNARY_OP_MAP: dict[type, str] = {
    ast.Invert: "~",
    ast.USub:   "-",
    ast.Not:    "not",
    ast.UAdd:   "+",
}

CMP_OP_MAP: dict[type, str] = {
    ast.Eq:    "==",
    ast.NotEq: "!=",
    ast.Lt:    "<",
    ast.Gt:    ">",
    ast.LtE:   "<=",
    ast.GtE:   ">=",
}

AUG_OP_MAP: dict[type, str] = {
    ast.Add:     "+",
    ast.Sub:     "-",
    ast.Mult:    "*",
    ast.BitOr:   "|",
    ast.BitAnd:  "&",
    ast.BitXor:  "^",
    ast.LShift:  "<<",
    ast.RShift:  ">>",
}


# =============================================================================
# PARSE ERROR
# =============================================================================

class FastPyParseError(Exception):
    """Raised when the parser encounters a Python construct it cannot handle."""

    def __init__(self, message: str, node: ast.AST = None):
        if node and hasattr(node, "lineno"):
            super().__init__(f"Line {node.lineno}: {message}")
        else:
            super().__init__(message)
        self.node = node


# =============================================================================
# EXPRESSION VISITOR
# Converts a single Python AST expression node into a FastPy IR expression.
# =============================================================================

class ExpressionVisitor:
    """
    Converts Python AST expression nodes to FastPy IR expression nodes.
    Called by StatementVisitor for every expression it encounters.
    """

    def visit(self, node: ast.expr) -> Any:
        method = f"visit_{type(node).__name__}"
        handler = getattr(self, method, self.visit_unsupported)
        return handler(node)

    def visit_unsupported(self, node: ast.expr) -> Any:
        raise FastPyParseError(
            f"Unsupported expression: '{type(node).__name__}'. "
            f"FastPy dialect requires explicit, statically-typed expressions.",
            node,
        )

    def visit_Constant(self, node: ast.Constant) -> IRLiteral:
        if isinstance(node.value, bool):
            return IRLiteral(value=node.value, kind="bool")
        if isinstance(node.value, int):
            return IRLiteral(value=node.value, kind="int")
        if node.value is None:
            return IRLiteral(value=None, kind="none")
        if isinstance(node.value, str):
            # String literals are not a FastPy type but are allowed through
            # so intrinsics.py can pattern-match bin(board).count("1") → POPCNT.
            return IRLiteral(value=node.value, kind="str")
        raise FastPyParseError(
            f"Unsupported literal type '{type(node.value).__name__}'. "
            f"FastPy supports integer and boolean literals only.",
            node,
        )

    def visit_Name(self, node: ast.Name) -> IRName:
        return IRName(name=node.id)

    def visit_BinOp(self, node: ast.BinOp) -> IRBinOp:
        op = BIN_OP_MAP.get(type(node.op))
        if op is None:
            raise FastPyParseError(
                f"Unsupported binary operator: '{type(node.op).__name__}'.", node
            )
        return IRBinOp(
            left=self.visit(node.left),
            op=op,
            right=self.visit(node.right),
        )

    def visit_UnaryOp(self, node: ast.UnaryOp) -> IRUnaryOp:
        op = UNARY_OP_MAP.get(type(node.op))
        if op is None:
            raise FastPyParseError(
                f"Unsupported unary operator: '{type(node.op).__name__}'.", node
            )
        return IRUnaryOp(op=op, operand=self.visit(node.operand))

    def visit_Compare(self, node: ast.Compare) -> IRCompare:
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise FastPyParseError(
                "FastPy does not support chained comparisons (e.g. `a < b < c`). "
                "Split into separate comparisons joined with `and`.",
                node,
            )
        op = CMP_OP_MAP.get(type(node.ops[0]))
        if op is None:
            raise FastPyParseError(
                f"Unsupported comparison operator: '{type(node.ops[0]).__name__}'.", node
            )
        return IRCompare(
            left=self.visit(node.left),
            op=op,
            right=self.visit(node.comparators[0]),
        )

    def visit_BoolOp(self, node: ast.BoolOp) -> IRBoolOp:
        op = "and" if isinstance(node.op, ast.And) else "or"
        return IRBoolOp(op=op, values=[self.visit(v) for v in node.values])

    def visit_Call(self, node: ast.Call) -> IRCall:
        receiver = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            obj = self.visit(node.func.value)
            if isinstance(obj, IRName):
                func_name = f"{obj.name}.{node.func.attr}"
            else:
                func_name = f"<expr>.{node.func.attr}"
                receiver = obj   # Preserve for intrinsics pattern matching
        else:
            raise FastPyParseError(
                "Unsupported call target. FastPy supports simple function "
                "calls and method calls only.",
                node,
            )
        return IRCall(func=func_name, args=[self.visit(a) for a in node.args], receiver=receiver)

    def visit_Attribute(self, node: ast.Attribute) -> IRAttribute:
        return IRAttribute(obj=self.visit(node.value), attr=node.attr)

    def visit_Subscript(self, node: ast.Subscript) -> IRSubscript:
        return IRSubscript(obj=self.visit(node.value), index=self.visit(node.slice))

    def visit_Tuple(self, node: ast.Tuple) -> IRTuple:
        return IRTuple(elements=[self.visit(e) for e in node.elts])

    def visit_IfExp(self, node: ast.IfExp) -> IRIfExp:
        return IRIfExp(
            condition=self.visit(node.test),
            body=self.visit(node.body),
            orelse=self.visit(node.orelse),
        )

    def visit_List(self, node: ast.List) -> IRLiteral:
        # Only empty list literals are allowed — as move-list placeholders
        if len(node.elts) == 0:
            return IRLiteral(value=[], kind="empty_list")
        raise FastPyParseError(
            "FastPy does not allow non-empty list literals inside compiled functions. "
            "Use fixed-size arrays: `moves: uint64[218]`.",
            node,
        )

    def _resolve_annotation(self, node: ast.expr) -> str:
        """Flatten a type annotation AST node to a string type name."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return str(node.value)
        if isinstance(node, ast.Subscript):
            # Handles Final[uint64], uint64[218]
            if isinstance(node.value, ast.Name):
                outer = node.value.id
                inner = self._resolve_annotation(node.slice)
                return f"{outer}[{inner}]"
        if isinstance(node, ast.Attribute):
            # Handles typing.Optional etc — not FastPy dialect but tolerated
            return node.attr
        return "unknown"


# =============================================================================
# STATEMENT VISITOR
# Converts Python AST statement nodes into FastPy IR statement nodes.
# =============================================================================

class StatementVisitor:
    """
    Converts Python AST statement nodes into FastPy IR statement nodes.
    Handles all statement types that can appear inside a function body.
    """

    def __init__(self):
        self.expr = ExpressionVisitor()

    def visit_body(self, stmts: list) -> list:
        """Convert a list of AST statements to a list of IR statements."""
        result = []
        for stmt in stmts:
            ir = self.visit(stmt)
            if ir is not None:
                result.append(ir)
        return result

    def visit(self, node: ast.stmt) -> Any:
        method = f"visit_{type(node).__name__}"
        handler = getattr(self, method, self.visit_unsupported)
        return handler(node)

    def visit_unsupported(self, node: ast.stmt) -> Any:
        raise FastPyParseError(
            f"Unsupported statement: '{type(node).__name__}'. "
            f"This construct is not part of the FastPy dialect.",
            node,
        )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> IRAssign:
        """Annotated assignment: `x: int32 = 0` or bare declaration `x: int32`"""
        target = self._resolve_target(node.target)
        type_name = self.expr._resolve_annotation(node.annotation)
        value = self.expr.visit(node.value) if node.value else None
        return IRAssign(target=target, value=value, type_name=type_name)

    def visit_Assign(self, node: ast.Assign) -> IRAssign:
        """Plain assignment: `best_move = 0`, `temp = knights`"""
        if len(node.targets) != 1:
            raise FastPyParseError(
                "FastPy does not support multi-target assignments. "
                "Assign each variable separately.",
                node,
            )
        target = self._resolve_target(node.targets[0])
        value = self.expr.visit(node.value)
        return IRAssign(target=target, value=value, type_name=None)

    def visit_AugAssign(self, node: ast.AugAssign) -> IRAugAssign:
        """Augmented assignment: `alpha += 1`, `board &= mask`"""
        op = AUG_OP_MAP.get(type(node.op))
        if op is None:
            raise FastPyParseError(
                f"Unsupported augmented operator: '{type(node.op).__name__}'.", node
            )
        return IRAugAssign(
            target=self._resolve_target(node.target),
            op=op,
            value=self.expr.visit(node.value),
        )

    def visit_Return(self, node: ast.Return) -> IRReturn:
        value = self.expr.visit(node.value) if node.value else IRLiteral(None, "none")
        return IRReturn(value=value)

    def visit_If(self, node: ast.If) -> IRIf:
        return IRIf(
            condition=self.expr.visit(node.test),
            body=self.visit_body(node.body),
            orelse=self.visit_body(node.orelse),
        )

    def visit_While(self, node: ast.While) -> IRWhile:
        return IRWhile(
            condition=self.expr.visit(node.test),
            body=self.visit_body(node.body),
        )

    def visit_For(self, node: ast.For) -> IRFor:
        return IRFor(
            target=self._resolve_target(node.target),
            iterable=self.expr.visit(node.iter),
            body=self.visit_body(node.body),
        )

    def visit_Break(self, node: ast.Break) -> IRBreak:
        return IRBreak()

    def visit_Expr(self, node: ast.Expr) -> Optional[IRExprStatement]:
        """Expression used as a statement — a call for its side effects, or a docstring."""
        # Skip docstrings (string constants at statement level)
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return IRExprStatement(expr=self.expr.visit(node.value))

    def visit_Pass(self, node: ast.Pass) -> None:
        return None

    def _resolve_target(self, node: ast.expr) -> str:
        """
        Flatten an assignment target to a flat string.

        Handles:
          x              → "x"
          self.field     → "self.field"
          moves[count]   → "moves[count]"   (simple Name index only)
          moves[0]       → "moves[0]"       (integer constant index)
        """
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                return f"{node.value.id}.{node.attr}"
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                obj = node.value.id
                # Accept Name or integer-constant indices — covers all engine patterns
                if isinstance(node.slice, ast.Name):
                    return f"{obj}[{node.slice.id}]"
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
                    return f"{obj}[{node.slice.value}]"
        raise FastPyParseError(
            f"Unsupported assignment target. "
            f"FastPy supports simple names, `self.attribute`, and `array[index]` only.",
            node,
        )


# =============================================================================
# MODULE VISITOR
# Walks the top-level AST of a source file and builds the final IRModule.
# =============================================================================

class ModuleVisitor:
    """
    Walks the top-level statements of a Python module and builds an IRModule.
    Handles type aliases, constants, functions, and class definitions.
    """

    def __init__(self, source_file: str):
        self.source_file = source_file
        self.type_aliases: list[IRTypeAlias] = []
        self.constants:    list[IRConstant]  = []
        self.functions:    list[IRFunction]  = []
        self.classes:      list[IRClass]     = []
        self.expr = ExpressionVisitor()
        self.stmt = StatementVisitor()

    def build(self, tree: ast.Module) -> IRModule:
        """Walk a parsed AST module and return a complete IRModule."""
        for node in tree.body:
            self._visit_top_level(node)
        return IRModule(
            source_file=self.source_file,
            type_aliases=self.type_aliases,
            constants=self.constants,
            functions=self.functions,
            classes=self.classes,
        )

    # -------------------------------------------------------------------------
    # Top-level dispatch
    # -------------------------------------------------------------------------

    def _visit_top_level(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Assign):
            self._try_type_alias(node)
        elif isinstance(node, ast.AnnAssign):
            self._try_constant(node)
        elif isinstance(node, ast.FunctionDef):
            self.functions.append(self._parse_function(node, is_method=False))
        elif isinstance(node, ast.ClassDef):
            self.classes.append(self._parse_class(node))
        # Imports, __main__ guards, and module docstrings are silently skipped

    # -------------------------------------------------------------------------
    # Type alias detection
    # -------------------------------------------------------------------------

    def _try_type_alias(self, node: ast.Assign) -> None:
        """
        Detect: `uint64 = int`
        These are the FastPy primitive type declarations.
        """
        if len(node.targets) != 1:
            return
        if not isinstance(node.targets[0], ast.Name):
            return
        if not isinstance(node.value, ast.Name):
            return

        name        = node.targets[0].id
        python_base = node.value.id

        # If the alias name itself has a known C++ mapping (e.g. uint64 → uint64_t),
        # use that directly rather than inheriting from the Python base type
        # (which would wrongly map uint64 = int → int32_t).
        if name in BUILTIN_TYPE_MAP:
            cpp_type = BUILTIN_TYPE_MAP[name]
        else:
            cpp_type = BUILTIN_TYPE_MAP.get(python_base)
            if cpp_type is None:
                return  # Not a recognised FastPy type alias

        alias = IRTypeAlias(name=name, cpp_type=cpp_type)
        self.type_aliases.append(alias)
        BUILTIN_TYPE_MAP[name] = cpp_type

    # -------------------------------------------------------------------------
    # Constant detection
    # -------------------------------------------------------------------------

    def _try_constant(self, node: ast.AnnAssign) -> None:
        """
        Detect: `FILE_A: Final[uint64] = 0x0101010101010101`
        These become C++ `constexpr` values — zero runtime cost.
        """
        if node.value is None:
            return

        annotation_str = self.expr._resolve_annotation(node.annotation)
        if not annotation_str.startswith("Final["):
            return

        type_name = annotation_str[len("Final["):-1]   # Strip Final[ and ]
        name = node.target.id if isinstance(node.target, ast.Name) else None
        if name is None:
            return

        value = self.expr.visit(node.value)
        self.constants.append(IRConstant(name=name, type_name=type_name, value=value))

    # -------------------------------------------------------------------------
    # Function parsing
    # -------------------------------------------------------------------------

    def _parse_function(self, node: ast.FunctionDef, is_method: bool) -> IRFunction:
        """Parse a FunctionDef AST node into an IRFunction."""
        params = []
        for arg in node.args.args:
            if arg.arg == "self":
                continue
            type_name = (
                self.expr._resolve_annotation(arg.annotation)
                if arg.annotation else "unknown"
            )
            params.append(IRParam(name=arg.arg, type_name=type_name))

        return_type = (
            self.expr._resolve_annotation(node.returns)
            if node.returns else "unknown"
        )

        # Drop leading docstring from function body before visiting statements
        body_stmts = node.body
        if (body_stmts
                and isinstance(body_stmts[0], ast.Expr)
                and isinstance(body_stmts[0].value, ast.Constant)
                and isinstance(body_stmts[0].value.value, str)):
            body_stmts = body_stmts[1:]

        body = self.stmt.visit_body(body_stmts)

        return IRFunction(
            name=node.name,
            params=params,
            return_type=return_type,
            body=body,
            is_method=is_method,
        )

    # -------------------------------------------------------------------------
    # Class parsing
    # -------------------------------------------------------------------------

    def _parse_class(self, node: ast.ClassDef) -> IRClass:
        """
        Parse a ClassDef AST node into an IRClass.
        Fields are extracted from __init__. All other methods are parsed normally.
        Compiled to a C++ struct.
        """
        fields:  list[IRField]    = []
        methods: list[IRFunction] = []

        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name == "__init__":
                fields = self._parse_init_fields(item)
            else:
                methods.append(self._parse_function(item, is_method=True))

        return IRClass(name=node.name, fields=fields, methods=methods)

    def _parse_init_fields(self, node: ast.FunctionDef) -> list[IRField]:
        """
        Extract field declarations from __init__.
        Looks for `self.field: type = value` patterns.
        """
        fields = []
        for stmt in node.body:
            if not isinstance(stmt, ast.AnnAssign):
                continue
            if not isinstance(stmt.target, ast.Attribute):
                continue
            if not isinstance(stmt.target.value, ast.Name):
                continue
            if stmt.target.value.id != "self":
                continue

            name      = stmt.target.attr
            type_name = self.expr._resolve_annotation(stmt.annotation)
            value     = self.expr.visit(stmt.value) if stmt.value else None
            fields.append(IRField(name=name, type_name=type_name, default_value=value))

        return fields


# =============================================================================
# PUBLIC API
# =============================================================================

def parse_file(source_file: str) -> IRModule:
    """
    Parse a FastPy dialect Python source file and return an IRModule.

    This is the primary entry point consumed by main.py, type_system.py,
    emitter.py, and intrinsics.py.

    Args:
        source_file: Path to the .py source file to parse.

    Returns:
        IRModule — the complete IR tree for the file.

    Raises:
        FastPyParseError: Unsupported Python construct encountered.
        FileNotFoundError: Source file does not exist.
        SyntaxError: Source file is not valid Python.
    """
    with open(source_file, "r", encoding="utf-8") as f:
        source = f.read()
    return parse_source(source, source_file=source_file)


def parse_source(source: str, source_file: str = "<string>") -> IRModule:
    """
    Parse FastPy dialect Python source code from a string.
    Useful for unit tests that don't need to touch the filesystem.

    Args:
        source:      Python source code as a string.
        source_file: Optional label for error messages (default: "<string>").

    Returns:
        IRModule — the complete IR tree.
    """
    try:
        tree = ast.parse(source, filename=source_file)
    except SyntaxError as e:
        raise SyntaxError(f"FastPy could not parse '{source_file}': {e}") from e

    visitor = ModuleVisitor(source_file=source_file)
    return visitor.build(tree)

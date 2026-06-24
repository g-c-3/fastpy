"""
FastPy C++ Emitter
==================
Walks an IRModule + TypeRegistry and emits a raw, zero-allocation C++ source file.

The emitter is a pure tree-walk: every IR node maps to exactly one C++ construct.
No analysis happens here — the type system has already validated the IR and the
registry has resolved all types.

Intrinsic substitution hook:
    Before emitting any expression, the emitter calls intrinsic_hook(node).
    If intrinsics.py recognises the pattern (e.g. bin(x).count("1") → POPCNT),
    it returns the C++ string directly. Otherwise the emitter falls back to
    baseline C++. This keeps the emitter clean and intrinsics.py self-contained.

Author: Gokul Chandar
Project: FastPy (github.com/g-c-3/fastpy)
License: MIT
"""

from __future__ import annotations

from typing import Optional, Callable

from .parser import (
    IRModule, IRFunction, IRClass, IRConstant,
    IRParam, IRField,
    IRAssign, IRAugAssign, IRReturn,
    IRIf, IRWhile, IRFor, IRBreak, IRExprStatement,
    IRName, IRLiteral, IRBinOp, IRUnaryOp,
    IRCompare, IRBoolOp, IRCall, IRAttribute,
    IRSubscript, IRTuple, IRIfExp,
)
from .type_system import TypeRegistry


# =============================================================================
# CPP WRITER
# Manages indentation and accumulates C++ output lines.
# =============================================================================

class CppWriter:
    """
    Thin wrapper around a line buffer with indentation tracking.
    The emitter writes to this; it never concatenates strings directly.
    """

    INDENT = "    "  # 4-space indent — matches Clang default

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._depth: int = 0

    def line(self, text: str = "") -> None:
        """Append one indented line to the buffer."""
        prefix = self.INDENT * self._depth
        self._lines.append(f"{prefix}{text}" if text else "")

    def blank(self) -> None:
        """Append a blank line."""
        self._lines.append("")

    def indent(self) -> None:
        self._depth += 1

    def dedent(self) -> None:
        self._depth = max(0, self._depth - 1)

    def get(self) -> str:
        """Return the complete buffered output as a single string."""
        return "\n".join(self._lines)


# =============================================================================
# EMIT ERROR
# =============================================================================

class EmitError(Exception):
    """Raised when the emitter encounters an IR node it cannot translate."""
    pass


# =============================================================================
# OPERATOR MAPS
# FastPy IR operator strings → C++ tokens.
# =============================================================================

_CPP_BIN_OP: dict[str, str] = {
    "+":  "+",
    "-":  "-",
    "*":  "*",
    "/":  "/",
    "//": "/",   # Integer floor div = C++ integer division for signed types
    "%":  "%",
    "<<": "<<",
    ">>": ">>",
    "|":  "|",
    "&":  "&",
    "^":  "^",
}

_CPP_UNARY_OP: dict[str, str] = {
    "~":   "~",
    "-":   "-",
    "+":   "+",
    "not": "!",
}

_CPP_AUG_OP: dict[str, str] = {
    "+":  "+=",
    "-":  "-=",
    "*":  "*=",
    "|":  "|=",
    "&":  "&=",
    "^":  "^=",
    "<<": "<<=",
    ">>": ">>=",
}

_CPP_BOOL_OP: dict[str, str] = {
    "and": "&&",
    "or":  "||",
}

_CPP_CMP_OP: dict[str, str] = {
    "==": "==",
    "!=": "!=",
    "<":  "<",
    ">":  ">",
    "<=": "<=",
    ">=": ">=",
}

# Bitwise operators need parentheses around their operands to guarantee
# correct precedence in generated C++ — C++ bitwise precedence is lower
# than comparison operators, which trips up even experienced C++ programmers.
_NEEDS_PARENS: set[str] = {"|", "&", "^", "<<", ">>"}


# =============================================================================
# CPP EMITTER
# =============================================================================

class CppEmitter:
    """
    Walks an IRModule and writes a complete C++ source file to a CppWriter.

    Call emit() to get the full source as a string.
    """

    def __init__(
        self,
        ir: IRModule,
        registry: TypeRegistry,
        intrinsic_hook: Optional[Callable] = None,
    ) -> None:
        self.ir       = ir
        self.registry = registry
        self.out      = CppWriter()
        # intrinsic_hook(node) → str | None
        # Supplied by intrinsics.py; None means no substitution for this node.
        self._intrinsic: Callable = intrinsic_hook or (lambda _: None)
        # Whether we are currently inside a struct method —
        # controls self. stripping in attribute/target resolution.
        self._in_method: bool = False

    # =========================================================================
    # TOP-LEVEL
    # =========================================================================

    def emit(self) -> str:
        """Emit the full C++ source file and return it as a string."""
        self._emit_file_header()
        self._emit_includes()
        self.out.blank()
        self._emit_forward_declarations()
        self.out.blank()
        self._emit_constants()
        self.out.blank()
        for cls in self.ir.classes:
            self._emit_class(cls)
            self.out.blank()
        for func in self.ir.functions:
            self._emit_function(func, in_struct=False)
            self.out.blank()
        return self.out.get()

    # =========================================================================
    # HEADER & INCLUDES
    # =========================================================================

    def _emit_file_header(self) -> None:
        self.out.line("// ================================================================")
        self.out.line("// FastPy-generated C++ — do not edit directly")
        self.out.line(f"// Source: {self.ir.source_file}")
        self.out.line("// ================================================================")
        self.out.blank()

    def _emit_includes(self) -> None:
        self.out.line("#include <cstdint>    // uint64_t, int32_t")
        self.out.line("#include <climits>    // INT_MAX, INT_MIN")
        self.out.line("#include <cstdio>     // printf  (UCI output)")
        self.out.line("#include <bit>        // std::popcount (C++20 fallback)")

    def _emit_forward_declarations(self) -> None:
        """
        Forward-declare all structs so functions that reference them compile
        regardless of definition order in the source file.
        """
        if not self.ir.classes:
            return
        self.out.line("// --- Forward declarations ---")
        for cls in self.ir.classes:
            self.out.line(f"struct {cls.name};")

    # =========================================================================
    # CONSTANTS
    # =========================================================================

    def _emit_constants(self) -> None:
        if not self.ir.constants:
            return
        self.out.line("// --- Constants ---")
        for c in self.ir.constants:
            cpp_type = self.registry.resolve(c.type_name)
            value    = self._fmt_constant_value(c.value, cpp_type)
            self.out.line(f"constexpr {cpp_type} {c.name} = {value};")

    def _fmt_constant_value(self, value_node, cpp_type: str) -> str:
        """
        Format a constant's value node, applying ULL suffix to uint64 literals
        so the C++ compiler treats them as unsigned 64-bit values.
        """
        if value_node is None:
            return "0"
        if cpp_type == "uint64_t" and isinstance(value_node, IRLiteral) \
                and value_node.kind == "int":
            return self._as_ull(value_node.value)
        # For NEG_INF: IRUnaryOp("-", IRLiteral(32767))
        if isinstance(value_node, IRUnaryOp) and value_node.op == "-":
            inner = self._emit_expr(value_node.operand)
            return f"-{inner}"
        return self._emit_expr(value_node)

    def _as_ull(self, value: int) -> str:
        """Format an integer as a C++ hex ULL literal."""
        if value > 0xFFFFFFFF:
            return f"0x{value:016X}ULL"
        if value > 0:
            return f"0x{value:08X}ULL"
        return f"{value}ULL"

    # =========================================================================
    # CLASS / STRUCT
    # =========================================================================

    def _emit_class(self, cls: IRClass) -> None:
        self.out.line(f"struct {cls.name} {{")
        self.out.indent()

        # Fields
        for f in cls.fields:
            cpp_type = self.registry.resolve(f.type_name)
            if f.default_value is not None:
                default = self._emit_expr(f.default_value)
                # ULL suffix for uint64 field defaults
                if cpp_type == "uint64_t" and isinstance(f.default_value, IRLiteral) \
                        and f.default_value.kind == "int":
                    default = self._as_ull(f.default_value.value)
                self.out.line(f"{cpp_type} {f.name} = {default};")
            else:
                self.out.line(f"{cpp_type} {f.name};")

        # Methods
        if cls.methods:
            self.out.blank()
            for method in cls.methods:
                self._emit_function(method, in_struct=True)
                self.out.blank()

        self.out.dedent()
        self.out.line(f"}};  // struct {cls.name}")

    # =========================================================================
    # FUNCTION
    # =========================================================================

    def _emit_function(self, func: IRFunction, in_struct: bool) -> None:
        self._in_method = in_struct

        ret_cpp = self.registry.resolve(func.return_type)
        if ret_cpp == "list":
            # Placeholder — resolve to void until move-list type is finalised
            ret_cpp = "void"

        params_str = ", ".join(
            f"{self.registry.resolve(p.type_name)} {p.name}"
            for p in func.params
        )

        const_suffix = " const" if in_struct else ""
        self.out.line(f"{ret_cpp} {func.name}({params_str}){const_suffix} {{")
        self.out.indent()
        self._emit_body(func.body)
        self.out.dedent()
        self.out.line("}")

        self._in_method = False

    # =========================================================================
    # BODY & STATEMENTS
    # =========================================================================

    def _emit_body(self, stmts: list) -> None:
        for stmt in stmts:
            self._emit_stmt(stmt)

    def _emit_stmt(self, stmt) -> None:
        t = type(stmt).__name__
        dispatch = {
            "IRAssign":        self._emit_assign,
            "IRAugAssign":     self._emit_aug_assign,
            "IRReturn":        self._emit_return,
            "IRIf":            self._emit_if,
            "IRWhile":         self._emit_while,
            "IRFor":           self._emit_for,
            "IRBreak":         lambda s: self.out.line("break;"),
            "IRExprStatement": lambda s: self.out.line(f"{self._emit_expr(s.expr)};"),
        }
        handler = dispatch.get(t)
        if handler:
            handler(stmt)
        else:
            self.out.line(f"/* TODO: unhandled statement {t} */")

    # ---- Assignment ----------------------------------------------------------

    def _emit_assign(self, stmt: IRAssign) -> None:
        target = self._strip_self(stmt.target)
        value  = self._emit_expr(stmt.value) if stmt.value is not None else None

        if stmt.type_name is not None:
            # Typed declaration
            if "[" in stmt.type_name:
                # Fixed-size array: `moves: uint64[218]` → `uint64_t moves[218] = {}`
                cpp_base, size = self.registry.resolve_array(stmt.type_name)
                if size > 0:
                    self.out.line(f"{cpp_base} {target}[{size}] = {{}};")
                    return
            cpp_type = self.registry.resolve(stmt.type_name)
            if value is not None:
                if cpp_type == "uint64_t" and isinstance(stmt.value, IRLiteral) \
                        and stmt.value.kind == "int":
                    value = self._as_ull(stmt.value.value)
                self.out.line(f"{cpp_type} {target} = {value};")
            else:
                self.out.line(f"{cpp_type} {target};")
        else:
            # Un-annotated re-assignment to an already-declared variable
            if value is not None:
                self.out.line(f"{target} = {value};")
            else:
                self.out.line(f"/* skipped: {target} = <empty> */")

    def _emit_aug_assign(self, stmt: IRAugAssign) -> None:
        target = self._strip_self(stmt.target)
        cpp_op = _CPP_AUG_OP.get(stmt.op, f"{stmt.op}=")
        value  = self._emit_expr(stmt.value)
        self.out.line(f"{target} {cpp_op} {value};")

    def _emit_return(self, stmt: IRReturn) -> None:
        if stmt.value is None:
            self.out.line("return;")
            return
        if isinstance(stmt.value, IRLiteral) and stmt.value.kind == "none":
            self.out.line("return;")
            return
        self.out.line(f"return {self._emit_expr(stmt.value)};")

    # ---- Control flow -------------------------------------------------------

    def _emit_if(self, stmt: IRIf) -> None:
        cond = self._emit_expr(stmt.condition)
        self.out.line(f"if ({cond}) {{")
        self.out.indent()
        self._emit_body(stmt.body)
        self.out.dedent()
        self._emit_orelse(stmt.orelse)

    def _emit_orelse(self, orelse: list) -> None:
        """
        Emit the else/elif branch of an if statement.
        Produces proper `} else if (cond) {` chains — not nested `} else { if`.
        """
        if not orelse:
            self.out.line("}")
            return

        # Single nested IRIf → elif chain
        if len(orelse) == 1 and type(orelse[0]).__name__ == "IRIf":
            elif_node = orelse[0]
            cond = self._emit_expr(elif_node.condition)
            self.out.line(f"}} else if ({cond}) {{")
            self.out.indent()
            self._emit_body(elif_node.body)
            self.out.dedent()
            self._emit_orelse(elif_node.orelse)
        else:
            # else block
            self.out.line("} else {")
            self.out.indent()
            self._emit_body(orelse)
            self.out.dedent()
            self.out.line("}")

    def _emit_while(self, stmt: IRWhile) -> None:
        cond = self._emit_expr(stmt.condition)
        self.out.line(f"while ({cond}) {{")
        self.out.indent()
        self._emit_body(stmt.body)
        self.out.dedent()
        self.out.line("}")

    def _emit_for(self, stmt: IRFor) -> None:
        """
        Translate Python for loops to C++ for loops.
          range(n)           → for (int32_t i = 0; i < n; i++)
          range(a, b)        → for (int32_t i = a; i < b; i++)
          range(a, b, step)  → for (int32_t i = a; i < b; i += step)
        Falls back to a comment for non-range iterables.
        """
        if isinstance(stmt.iterable, IRCall) and stmt.iterable.func == "range":
            args = stmt.iterable.args
            if len(args) == 1:
                start, stop, step = "0", self._emit_expr(args[0]), None
            elif len(args) == 2:
                start = self._emit_expr(args[0])
                stop  = self._emit_expr(args[1])
                step  = None
            elif len(args) == 3:
                start = self._emit_expr(args[0])
                stop  = self._emit_expr(args[1])
                step  = self._emit_expr(args[2])
            else:
                start, stop, step = "0", "0", None

            t = stmt.target
            inc = f"{t}++" if step is None else f"{t} += {step}"
            self.out.line(f"for (int32_t {t} = {start}; {t} < {stop}; {inc}) {{")
        else:
            iterable = self._emit_expr(stmt.iterable)
            self.out.line(f"/* TODO: for {stmt.target} in {iterable} */ {{")

        self.out.indent()
        self._emit_body(stmt.body)
        self.out.dedent()
        self.out.line("}")

    # =========================================================================
    # EXPRESSION EMISSION
    # Returns a C++ expression string. Never writes to self.out directly.
    # =========================================================================

    def _emit_expr(self, node) -> str:
        if node is None:
            return ""

        # Intrinsic hook — intrinsics.py gets first look at every expression
        result = self._intrinsic(node)
        if result is not None:
            return result

        t = type(node).__name__

        if t == "IRLiteral":     return self._emit_literal(node)
        if t == "IRName":        return self._strip_self(node.name)
        if t == "IRBinOp":       return self._emit_binop(node)
        if t == "IRUnaryOp":     return self._emit_unaryop(node)
        if t == "IRCompare":     return self._emit_compare(node)
        if t == "IRBoolOp":      return self._emit_boolop(node)
        if t == "IRCall":        return self._emit_call(node)
        if t == "IRAttribute":   return self._emit_attribute(node)
        if t == "IRSubscript":   return self._emit_subscript(node)
        if t == "IRTuple":       return self._emit_tuple(node)
        if t == "IRIfExp":       return self._emit_ifexp(node)

        return f"/* unhandled expr: {t} */"

    def _emit_literal(self, node: IRLiteral) -> str:
        if node.kind == "bool":
            return "true" if node.value else "false"
        if node.kind == "none":
            return "/* void */"
        if node.kind == "int":
            return str(node.value)
        if node.kind == "str":
            # String literals only appear inside bin(x).count("1") patterns.
            # intrinsics.py replaces the whole call; this is the safe fallback.
            return f'"{node.value}"'
        if node.kind == "empty_list":
            return "{}"
        return "0"

    def _emit_binop(self, node: IRBinOp) -> str:
        cpp_op = _CPP_BIN_OP.get(node.op, node.op)
        left   = self._emit_expr(node.left)
        right  = self._emit_expr(node.right)
        # Bitwise operators: wrap operands in parens to guard precedence
        if node.op in _NEEDS_PARENS:
            return f"({left} {cpp_op} {right})"
        return f"{left} {cpp_op} {right}"

    def _emit_unaryop(self, node: IRUnaryOp) -> str:
        cpp_op  = _CPP_UNARY_OP.get(node.op, node.op)
        operand = self._emit_expr(node.operand)
        return f"{cpp_op}{operand}"

    def _emit_compare(self, node: IRCompare) -> str:
        cpp_op = _CPP_CMP_OP.get(node.op, node.op)
        left   = self._emit_expr(node.left)
        right  = self._emit_expr(node.right)
        return f"{left} {cpp_op} {right}"

    def _emit_boolop(self, node: IRBoolOp) -> str:
        cpp_op = _CPP_BOOL_OP.get(node.op, node.op)
        # Each operand wrapped in parens for safe short-circuit precedence
        parts  = [f"({self._emit_expr(v)})" for v in node.values]
        return f" {cpp_op} ".join(parts)

    def _emit_call(self, node: IRCall) -> str:
        args_str = ", ".join(self._emit_expr(a) for a in node.args)
        func     = node.func

        # Strip self. from method calls when inside a struct
        if self._in_method and func.startswith("self."):
            func = func[len("self."):]

        # bin(x).count("1") — intrinsics.py replaces this whole node.
        # If it didn't intercept (no hook), emit a readable TODO.
        if func == "<expr>.count":
            return f"/* TODO intrinsic: __builtin_popcountll({args_str}) */"

        return f"{func}({args_str})"

    def _emit_attribute(self, node: IRAttribute) -> str:
        obj = self._emit_expr(node.obj)
        if self._in_method and obj == "self":
            return node.attr
        return f"{obj}.{node.attr}"

    def _emit_subscript(self, node: IRSubscript) -> str:
        obj   = self._emit_expr(node.obj)
        index = self._emit_expr(node.index)
        return f"{obj}[{index}]"

    def _emit_tuple(self, node: IRTuple) -> str:
        # C++ has no tuple literals in expression context —
        # emit as comma-separated values (valid for multi-return via struct later)
        return ", ".join(self._emit_expr(e) for e in node.elements)

    def _emit_ifexp(self, node: IRIfExp) -> str:
        cond   = self._emit_expr(node.condition)
        body   = self._emit_expr(node.body)
        orelse = self._emit_expr(node.orelse)
        return f"({cond} ? {body} : {orelse})"

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _strip_self(self, name: str) -> str:
        """Remove `self.` prefix from a name when emitting inside a struct method."""
        if self._in_method and name.startswith("self."):
            return name[len("self."):]
        return name


# =============================================================================
# PUBLIC API
# =============================================================================

def emit_module(
    ir: IRModule,
    registry: TypeRegistry,
    intrinsic_hook: Optional[Callable] = None,
) -> str:
    """
    Emit a complete C++ source file from an IRModule and TypeRegistry.

    Args:
        ir:              IRModule from parser.parse_file()
        registry:        TypeRegistry from type_system.check_module()
        intrinsic_hook:  Optional callable(node) -> str | None
                         Provided by intrinsics.py. Called before every
                         expression node is emitted. Return a C++ string
                         to override baseline emission, or None to fall back.

    Returns:
        A complete C++ source file as a string.
        Write it to disk and pass it to toolchain.compile().

    Usage:
        from fastpy.core.parser      import parse_file
        from fastpy.core.type_system  import check_module
        from fastpy.core.emitter      import emit_module

        ir     = parse_file("engine.py")
        result = check_module(ir)

        if result.ok:
            cpp = emit_module(ir, result.registry)
            with open("engine.cpp", "w") as f:
                f.write(cpp)
    """
    return CppEmitter(ir, registry, intrinsic_hook).emit()

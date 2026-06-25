"""
FastPy Type System — Strict Type Enforcer
==========================================
Consumes an IRModule produced by parser.py and:

  1. Builds a complete TypeRegistry (FastPy name → C++ type string)
  2. Fixes alias resolution — `uint64 = int` correctly maps to
     `uint64_t`, not `int`'s mapping of `int32_t`
  3. Validates that every parameter, return type, and first-use
     variable declaration is explicitly annotated
  4. Exposes resolve() and resolve_array() for the emitter

The type system does NOT generate C++ — that is emitter.py's job.

Author: Gokul Chandar
Project: FastPy (github.com/g-c-3/fastpy)
License: MIT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .parser import (
    IRModule, IRTypeAlias, IRConstant,
    IRFunction, IRClass, IRParam, IRField,
    IRAssign, IRAugAssign, IRReturn,
    IRIf, IRWhile, IRFor, IRBreak,
    IRExprStatement,
)


# =============================================================================
# GROUND-TRUTH C++ TYPE TABLE
# This is the authoritative source — never derived from Python base types.
# The parser's BUILTIN_TYPE_MAP is only used for initial alias discovery;
# all final C++ types come from here.
# =============================================================================

_CPP_TYPE_TABLE: dict[str, str] = {
    # FastPy dialect primitives
    "uint64":  "uint64_t",
    "int32":   "int32_t",
    "bool8":   "bool",
    # Python built-ins that appear in FastPy code
    "int":     "int32_t",
    "bool":    "bool",
    "None":    "void",
    # C++ types used directly (passthrough)
    "uint64_t": "uint64_t",
    "int32_t":  "int32_t",
    "int64_t":  "int64_t",
    "uint32_t": "uint32_t",
    "void":     "void",
    # Python-mode types — valid for the type checker, flagged by the emitter.
    # `list`  → replace with `uint64[218]` for zero-allocation C++ compilation.
    # `tuple` → replace with a packed uint64 move encoding.
    "list":   "/* list: use uint64[218] for zero-allocation C++ */",
    "tuple":  "/* tuple: use a packed uint64 move encoding */",
}


# =============================================================================
# TYPE ERROR
# =============================================================================

@dataclass
class TypeCheckError:
    """A single type validation failure."""
    location: str   # e.g. "popcount() param board"
    message: str

    def __str__(self) -> str:
        return f"[TYPE ERROR] {self.location}: {self.message}"


# =============================================================================
# TYPE REGISTRY
# The single source of truth for type resolution used by the emitter.
# =============================================================================

class TypeRegistry:
    """
    Maps FastPy dialect type names to their C++ equivalents.

    Built from the ground-truth table plus any type aliases discovered
    in the source file. The emitter calls resolve() and resolve_array()
    to get C++ type strings for every variable and parameter.
    """

    def __init__(self) -> None:
        # Start from the ground-truth table — never from Python base mappings
        self._map: dict[str, str] = dict(_CPP_TYPE_TABLE)

    def register_alias(self, alias: IRTypeAlias) -> None:
        """
        Register a type alias from the source file.

        Critically: if the alias name is already in the ground-truth table
        (e.g. `uint64`), we use the ground-truth mapping — not whatever
        Python base type the alias was written against.

        Example:
            `uint64 = int`  →  name="uint64", python_base mapped "int32_t"
            But ground truth says uint64 → uint64_t, so we keep that.
        """
        name = alias.name
        if name in _CPP_TYPE_TABLE:
            # Ground truth wins — do not overwrite with the Python base mapping
            self._map[name] = _CPP_TYPE_TABLE[name]
        else:
            # New alias not in ground truth — accept the parser's derivation
            self._map[name] = alias.cpp_type

    def resolve(self, type_name: str) -> str:
        """
        Resolve a FastPy type name to its C++ equivalent.

        Strips Final[] wrappers before resolving.
        Returns the C++ type string, or "/* unknown */" with a note if
        the type cannot be resolved (type_system validates these away).

        Examples:
            resolve("uint64")         → "uint64_t"
            resolve("int32")          → "int32_t"
            resolve("Final[uint64]")  → "uint64_t"
            resolve("BoardState")     → "BoardState"  (passthrough for structs)
        """
        # Strip Final[...] wrapper
        if type_name.startswith("Final[") and type_name.endswith("]"):
            type_name = type_name[len("Final["):-1]

        # Strip array suffix — resolve_array() handles the full form
        if "[" in type_name:
            base = type_name[:type_name.index("[")]
            return self._map.get(base, base)

        return self._map.get(type_name, type_name)   # Passthrough for structs

    def resolve_array(self, type_name: str) -> tuple[str, int]:
        """
        Resolve a fixed-size array type to a (C++ element type, size) pair.

        Example:
            resolve_array("uint64[218]") → ("uint64_t", 218)

        Returns ("unknown", 0) if the type is not an array annotation.
        """
        if "[" not in type_name or not type_name.endswith("]"):
            return (self.resolve(type_name), 0)

        bracket = type_name.index("[")
        base    = type_name[:bracket]
        size_str = type_name[bracket + 1:-1]

        cpp_base = self._map.get(base, base)
        try:
            size = int(size_str)
        except ValueError:
            size = 0

        return (cpp_base, size)

    def is_known(self, type_name: str) -> bool:
        """Return True if the type name resolves to a known C++ type."""
        if type_name in ("unknown", "", "unknown_type"):
            return False
        clean = type_name
        if clean.startswith("Final["):
            clean = clean[len("Final["):-1]
        if "[" in clean:
            clean = clean[:clean.index("[")]
        # Known if it's in our map OR it looks like a struct name (PascalCase)
        return clean in self._map or (clean and clean[0].isupper())

    def __repr__(self) -> str:
        entries = ", ".join(f"{k}→{v}" for k, v in sorted(self._map.items()))
        return f"TypeRegistry({entries})"


# =============================================================================
# TYPE CHECK RESULT
# =============================================================================

@dataclass
class TypeCheckResult:
    """
    The output of check_module().
    Consumed by emitter.py and main.py.
    """
    registry: TypeRegistry
    errors:   list[TypeCheckError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True if there are zero type errors."""
        return len(self.errors) == 0

    def report(self) -> str:
        """Return a human-readable error report, or a success message."""
        if self.ok:
            return "Type check passed — zero errors."
        lines = [f"Type check failed — {len(self.errors)} error(s):\n"]
        for i, err in enumerate(self.errors, 1):
            lines.append(f"  {i}. {err}")
        return "\n".join(lines)


# =============================================================================
# TYPE CHECKER
# Walks an IRModule and validates all type annotations.
# =============================================================================

class TypeChecker:
    """
    Walks the IR tree produced by parser.py and validates type annotations.

    Rules enforced:
      - Every function parameter must have an explicit, known type annotation
      - Every function return type must be explicitly annotated
      - Every first-use variable declaration inside a function must be annotated
        (bare `x = value` without a prior `x: type` is flagged)
      - Class fields must all be typed
      - Array types must have a valid integer size (e.g. uint64[218])
    """

    def __init__(self, registry: TypeRegistry) -> None:
        self.registry = registry
        self.errors:  list[TypeCheckError] = []

    # -------------------------------------------------------------------------
    # Module-level entry point
    # -------------------------------------------------------------------------

    def check_module(self, ir: IRModule) -> None:
        """Walk the entire IRModule and collect all type errors."""
        for alias in ir.type_aliases:
            self.registry.register_alias(alias)

        for constant in ir.constants:
            self._check_constant(constant)

        for func in ir.functions:
            self._check_function(func, context="")

        for cls in ir.classes:
            self._check_class(cls)

    # -------------------------------------------------------------------------
    # Constant checking
    # -------------------------------------------------------------------------

    def _check_constant(self, constant: IRConstant) -> None:
        loc = f"constant {constant.name}"
        if not self.registry.is_known(constant.type_name):
            self._error(loc, f"unknown type '{constant.type_name}'")

    # -------------------------------------------------------------------------
    # Function checking
    # -------------------------------------------------------------------------

    def _check_function(self, func: IRFunction, context: str) -> None:
        prefix = f"{context}.{func.name}()" if context else f"{func.name}()"

        # Check all parameters
        for param in func.params:
            loc = f"{prefix} param '{param.name}'"
            if param.type_name == "unknown":
                self._error(
                    loc,
                    f"missing type annotation. "
                    f"FastPy requires explicit types on all parameters. "
                    f"Example: `{param.name}: int32`"
                )
            elif not self.registry.is_known(param.type_name):
                self._error(loc, f"unknown type '{param.type_name}'")

        # Check return type
        ret_loc = f"{prefix} return type"
        if func.return_type == "unknown":
            self._error(
                ret_loc,
                f"missing return type annotation. "
                f"FastPy requires explicit return types. "
                f"Example: `def {func.name}(...) -> int32:`"
            )
        elif func.return_type not in ("unknown",) and \
                not self.registry.is_known(func.return_type) and \
                func.return_type != "list":
            # "list" is a temporary placeholder — intrinsics.py will resolve it
            self._error(ret_loc, f"unknown return type '{func.return_type}'")

        # Track declared variables inside the function body
        declared: set[str] = {p.name for p in func.params}
        self._check_body(func.body, declared, prefix)

    # -------------------------------------------------------------------------
    # Class checking
    # -------------------------------------------------------------------------

    def _check_class(self, cls: IRClass) -> None:
        # Check all fields
        for f in cls.fields:
            loc = f"class {cls.name} field '{f.name}'"
            if not self.registry.is_known(f.type_name):
                self._error(loc, f"unknown type '{f.type_name}'")

        # Check all methods
        for method in cls.methods:
            self._check_function(method, context=cls.name)

    # -------------------------------------------------------------------------
    # Body / statement checking
    # -------------------------------------------------------------------------

    def _check_body(
        self,
        body: list,
        declared: set[str],
        func_name: str,
    ) -> None:
        """
        Walk a list of IR statements, tracking declared variables.
        The `declared` set is updated in-place so nested blocks share scope.
        """
        for stmt in body:
            self._check_stmt(stmt, declared, func_name)

    def _check_stmt(
        self,
        stmt,
        declared: set[str],
        func_name: str,
    ) -> None:
        stmt_type = type(stmt).__name__

        if stmt_type == "IRAssign":
            self._check_assign(stmt, declared, func_name)

        elif stmt_type == "IRAugAssign":
            # Target must already be declared
            if stmt.target not in declared:
                self._error(
                    f"{func_name} stmt",
                    f"'{stmt.target}' used in augmented assignment before declaration."
                )

        elif stmt_type == "IRReturn":
            pass  # Return value type-checking deferred to emitter

        elif stmt_type == "IRIf":
            self._check_body(stmt.body,  declared, func_name)
            self._check_body(stmt.orelse, declared, func_name)

        elif stmt_type == "IRWhile":
            self._check_body(stmt.body, declared, func_name)

        elif stmt_type == "IRFor":
            declared.add(stmt.target)
            self._check_body(stmt.body, declared, func_name)

        elif stmt_type in ("IRBreak", "IRExprStatement"):
            pass  # No type checks needed

    def _check_assign(
        self,
        stmt: IRAssign,
        declared: set[str],
        func_name: str,
    ) -> None:
        target   = stmt.target
        loc      = f"{func_name} var '{target}'"
        is_first = target not in declared

        if stmt.type_name is not None:
            # Annotated declaration — validate the type
            if not self.registry.is_known(stmt.type_name):
                # Array types need their base type checked
                if "[" in stmt.type_name:
                    cpp_type, size = self.registry.resolve_array(stmt.type_name)
                    if size <= 0:
                        self._error(
                            loc,
                            f"array type '{stmt.type_name}' has invalid size. "
                            f"Example: `moves: uint64[218]`"
                        )
                    elif cpp_type == stmt.type_name[:stmt.type_name.index("[")]:
                        self._error(
                            loc,
                            f"unknown array element type in '{stmt.type_name}'"
                        )
                else:
                    self._error(loc, f"unknown type '{stmt.type_name}'")
            declared.add(target)

        else:
            # Un-annotated assignment
            if is_first and not target.startswith("self."):
                # First use without a type annotation — flag it
                self._error(
                    loc,
                    f"first assignment to '{target}' has no type annotation. "
                    f"FastPy requires types on all first-use declarations. "
                    f"Example: `{target}: int32 = {_placeholder_value(target)}`"
                )
            else:
                declared.add(target)

    # -------------------------------------------------------------------------
    # Error helper
    # -------------------------------------------------------------------------

    def _error(self, location: str, message: str) -> None:
        self.errors.append(TypeCheckError(location=location, message=message))


# =============================================================================
# HELPERS
# =============================================================================

def _placeholder_value(name: str) -> str:
    """Return a sensible placeholder value for error messages."""
    if "count" in name or "num" in name or "depth" in name:
        return "0"
    if "score" in name or "eval" in name or "val" in name:
        return "0"
    if "board" in name or "mask" in name or "bb" in name:
        return "0"
    return "0"


# =============================================================================
# PUBLIC API
# =============================================================================

def check_module(ir: IRModule) -> TypeCheckResult:
    """
    Run the full type check on an IRModule.

    Builds the TypeRegistry, registers all type aliases with correct
    C++ mappings, validates all annotations, and returns a TypeCheckResult.

    Args:
        ir: The IRModule produced by parser.parse_file() or parser.parse_source()

    Returns:
        TypeCheckResult with:
          .registry  — TypeRegistry for the emitter to use
          .errors    — list of TypeCheckError (empty if all types are valid)
          .ok        — True if zero errors

    Usage:
        from fastpy.core.parser import parse_file
        from fastpy.core.type_system import check_module

        ir     = parse_file("engine.py")
        result = check_module(ir)

        if not result.ok:
            print(result.report())
        else:
            # Pass result.registry to emitter
            ...
    """
    registry = TypeRegistry()
    checker  = TypeChecker(registry)
    checker.check_module(ir)
    return TypeCheckResult(registry=registry, errors=checker.errors)

"""
FastPy core package.

Exports the primary public API used by main.py and external callers:

    from core.parser      import parse_file, parse_source, FastPyParseError, IRModule
    from core.type_system  import check_module, TypeRegistry, TypeCheckResult
    from core.emitter      import emit_module
    from core.intrinsics   import IntrinsicMapper, list_patterns
    from core.toolchain    import compile_cpp, find_compiler, CompilerNotFoundError

Each sub-module has exactly one responsibility:
  parser      → Python source → FastPy IR
  type_system → IR → TypeRegistry + error list
  emitter     → IR + TypeRegistry → C++ string
  intrinsics  → IR expression node → hardware intrinsic C++ string (or None)
  toolchain   → C++ string → native binary
"""

from .parser      import parse_file, parse_source, FastPyParseError, IRModule
from .type_system  import check_module, TypeRegistry, TypeCheckResult
from .emitter      import emit_module
from .intrinsics   import IntrinsicMapper, list_patterns
from .toolchain    import compile_cpp, find_compiler, CompilerNotFoundError

__all__ = [
    # Parser
    "parse_file",
    "parse_source",
    "FastPyParseError",
    "IRModule",
    # Type system
    "check_module",
    "TypeRegistry",
    "TypeCheckResult",
    # Emitter
    "emit_module",
    # Intrinsics
    "IntrinsicMapper",
    "list_patterns",
    # Toolchain
    "compile_cpp",
    "find_compiler",
    "CompilerNotFoundError",
]

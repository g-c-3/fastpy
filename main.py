"""
FastPy CLI — Entry Point
========================
The single command that drives the full FastPy pipeline:

    fastpy build engine.py --optimize=O3

Pipeline:
    1. parser.parse_file()      →  IRModule
    2. type_system.check_module() →  TypeCheckResult + TypeRegistry
    3. emitter.emit_module()    →  C++ source string
    4. toolchain.compile_cpp()  →  Native binary

Commands:
    fastpy build <file>         Compile a FastPy source file
    fastpy check <file>         Type-check only — no C++ output
    fastpy emit <file>          Emit C++ only — no compilation
    fastpy intrinsics           List all hardware intrinsic patterns

Author: Gokul Chandar
Project: FastPy (github.com/g-c-3/fastpy)
License: MIT
"""

import sys
import argparse
from pathlib import Path


# =============================================================================
# VERSION
# =============================================================================

FASTPY_VERSION = "0.1.0-dev"


# =============================================================================
# PIPELINE
# =============================================================================

def run_pipeline(
    source_file: str,
    output_path: str,
    opt_level:   str,
    compiler:    str,
    keep_cpp:    bool,
    verbose:     bool,
) -> int:
    """
    Run the full FastPy build pipeline on a source file.
    Returns an exit code: 0 for success, 1 for failure.
    """
    from core.parser      import parse_file, FastPyParseError
    from core.type_system  import check_module
    from core.emitter      import emit_module
    from core.toolchain    import compile_cpp, find_compiler, compiler_version, \
                                   CompilerNotFoundError

    source_path = Path(source_file)
    if not source_path.exists():
        print(f"fastpy: error: file not found: {source_file}", file=sys.stderr)
        return 1

    # ── Step 1: Parse ────────────────────────────────────────────────────────
    _step("Parsing", source_file, verbose)
    try:
        ir = parse_file(source_file)
    except (FastPyParseError, SyntaxError) as e:
        print(f"\nfastpy: parse error: {e}", file=sys.stderr)
        return 1

    if verbose:
        print(
            f"         {len(ir.functions)} function(s), "
            f"{len(ir.classes)} class(es), "
            f"{len(ir.constants)} constant(s)"
        )

    # ── Step 2: Type-check ───────────────────────────────────────────────────
    _step("Type checking", source_file, verbose)
    result = check_module(ir)

    if not result.ok:
        print(f"\n{result.report()}", file=sys.stderr)
        print(
            f"\nfastpy: {len(result.errors)} type error(s). "
            f"Fix them to continue.",
            file=sys.stderr,
        )
        return 1

    if verbose:
        print("         All types valid")

    # ── Step 3: Emit C++ ─────────────────────────────────────────────────────
    _step("Emitting C++", source_file, verbose)
    cpp_source = emit_module(ir, result.registry)

    if verbose:
        line_count = cpp_source.count("\n")
        print(f"         {line_count} lines of C++ generated")

    # ── Step 4: Compile ──────────────────────────────────────────────────────
    try:
        found_compiler = find_compiler(prefer=compiler or None)
    except CompilerNotFoundError as e:
        print(f"\nfastpy: {e}", file=sys.stderr)
        return 1

    if verbose:
        print(f"\nCompiling  [{compiler_version(found_compiler)}]")
        print(f"           -O{opt_level} -march=native -mpopcnt -mbmi -mbmi2")
    else:
        _step("Compiling", f"-{opt_level} -march=native", verbose=True)

    compile_result = compile_cpp(
        cpp_source=cpp_source,
        output_path=output_path,
        opt_level=opt_level,
        compiler=found_compiler,
        keep_cpp=keep_cpp,
    )

    if not compile_result.ok:
        print(f"\nfastpy: compilation failed:\n", file=sys.stderr)
        print(compile_result.stderr, file=sys.stderr)
        return 1

    # ── Done ─────────────────────────────────────────────────────────────────
    print(f"\n✅  {source_file} → {compile_result.binary_path}")
    if verbose and compile_result.stderr:
        print(f"\nCompiler warnings:\n{compile_result.stderr}")

    return 0


def run_check(source_file: str, verbose: bool) -> int:
    """
    Type-check only — no C++ output, no compilation.
    Returns 0 if all types are valid, 1 if there are errors.
    """
    from core.parser      import parse_file, FastPyParseError
    from core.type_system  import check_module

    if not Path(source_file).exists():
        print(f"fastpy: error: file not found: {source_file}", file=sys.stderr)
        return 1

    try:
        ir = parse_file(source_file)
    except (FastPyParseError, SyntaxError) as e:
        print(f"fastpy: parse error: {e}", file=sys.stderr)
        return 1

    result = check_module(ir)
    print(result.report())

    if not result.ok:
        print(f"\nfastpy check: {len(result.errors)} error(s) in {source_file}")
        return 1

    print(f"fastpy check: {source_file} — OK")
    return 0


def run_emit(source_file: str, output_cpp: str, verbose: bool) -> int:
    """
    Emit C++ only — parse and emit, no type validation, no compilation.
    Useful for inspecting what FastPy generates before compiling.
    """
    from core.parser      import parse_file, FastPyParseError
    from core.type_system  import check_module
    from core.emitter      import emit_module

    if not Path(source_file).exists():
        print(f"fastpy: error: file not found: {source_file}", file=sys.stderr)
        return 1

    try:
        ir = parse_file(source_file)
    except (FastPyParseError, SyntaxError) as e:
        print(f"fastpy: parse error: {e}", file=sys.stderr)
        return 1

    result  = check_module(ir)
    cpp     = emit_module(ir, result.registry)

    Path(output_cpp).write_text(cpp, encoding="utf-8")
    print(f"✅  C++ written to {output_cpp}")

    if not result.ok:
        print(
            f"\n⚠️   {len(result.errors)} type warning(s) — "
            f"fix before compiling:",
            file=sys.stderr,
        )
        for err in result.errors:
            print(f"     {err}", file=sys.stderr)

    return 0


def run_list_intrinsics() -> int:
    """Print the registered hardware intrinsic pattern table."""
    from core.intrinsics import list_patterns
    print(list_patterns())
    return 0


# =============================================================================
# CLI
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fastpy",
        description="FastPy — Python-to-C++ transpiler for chess engines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  fastpy build engine.py\n"
            "  fastpy build engine.py -o my_engine --optimize O3\n"
            "  fastpy check engine.py\n"
            "  fastpy emit  engine.py -o engine.cpp\n"
            "  fastpy intrinsics\n"
        ),
    )
    p.add_argument(
        "--version", action="version",
        version=f"FastPy {FASTPY_VERSION}",
    )

    sub = p.add_subparsers(dest="command", metavar="command")

    # ── build ─────────────────────────────────────────────────────────────────
    build = sub.add_parser(
        "build",
        help="Compile a FastPy source file to a native binary",
    )
    build.add_argument("source", help="FastPy source file (e.g. engine.py)")
    build.add_argument(
        "-o", "--output",
        default=None,
        help="Output binary path (default: source filename without .py)",
    )
    build.add_argument(
        "--optimize",
        default="O3",
        choices=["O0", "O1", "O2", "O3", "Os"],
        metavar="LEVEL",
        help="Optimization level: O0 O1 O2 O3 Os (default: O3)",
    )
    build.add_argument(
        "--compiler",
        default=None,
        metavar="NAME",
        help="Force a specific compiler: clang++ or g++ (default: auto-detect)",
    )
    build.add_argument(
        "--keep-cpp",
        action="store_true",
        help="Keep the generated .cpp file alongside the binary",
    )
    build.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed pipeline progress",
    )

    # ── check ─────────────────────────────────────────────────────────────────
    check = sub.add_parser(
        "check",
        help="Type-check a FastPy source file without compiling",
    )
    check.add_argument("source", help="FastPy source file")
    check.add_argument("-v", "--verbose", action="store_true")

    # ── emit ──────────────────────────────────────────────────────────────────
    emit = sub.add_parser(
        "emit",
        help="Emit C++ from a FastPy source file without compiling",
    )
    emit.add_argument("source", help="FastPy source file")
    emit.add_argument(
        "-o", "--output",
        default=None,
        help="Output .cpp path (default: source filename with .cpp extension)",
    )
    emit.add_argument("-v", "--verbose", action="store_true")

    # ── intrinsics ────────────────────────────────────────────────────────────
    sub.add_parser(
        "intrinsics",
        help="List all hardware intrinsic patterns FastPy recognises",
    )

    return p


def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "build":
        source  = args.source
        output  = args.output or str(Path(source).with_suffix(""))
        return run_pipeline(
            source_file=source,
            output_path=output,
            opt_level=args.optimize,
            compiler=args.compiler,
            keep_cpp=args.keep_cpp,
            verbose=args.verbose,
        )

    if args.command == "check":
        return run_check(args.source, args.verbose)

    if args.command == "emit":
        output = args.output or str(Path(args.source).with_suffix(".cpp"))
        return run_emit(args.source, output, args.verbose)

    if args.command == "intrinsics":
        return run_list_intrinsics()

    parser.print_help()
    return 0


# =============================================================================
# HELPERS
# =============================================================================

def _step(label: str, detail: str, verbose: bool) -> None:
    if verbose:
        print(f"\n{label:<14} {detail}")
    else:
        print(f"  {label}...", end=" ", flush=True)
        if not verbose:
            print()


# =============================================================================
# ENTRY
# =============================================================================

if __name__ == "__main__":
    sys.exit(main())

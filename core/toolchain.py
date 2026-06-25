"""
FastPy Compiler Bridge — GCC/Clang Toolchain
=============================================
Writes emitted C++ to disk and invokes GCC or Clang with maximum
optimization flags to produce a native binary.

Compiler flags used:
    -O3               Maximum optimization — enables auto-vectorisation,
                      loop unrolling, inlining, and constant folding
    -march=native     Tune for the exact CPU running the build — unlocks
                      POPCNT, TZCNT, BMI1, BMI2, AVX2 where available
    -std=c++20        C++20 required for <bit> (std::popcount fallback)
    -mpopcnt          Explicitly enable POPCNT instruction
    -mbmi             Enable BMI1: BLSI, BLSR, TZCNT
    -mbmi2            Enable BMI2: PEXT, PDEP (magic bitboard generation)
    -fno-exceptions   No exception overhead — chess engines never throw
    -fno-rtti         No RTTI overhead — no dynamic_cast needed
    -Wall -Wextra     Full warnings during development

Author: Gokul Chandar
Project: FastPy (github.com/g-c-3/fastpy)
License: MIT
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# =============================================================================
# COMPILER FLAGS
# =============================================================================

# Base flags applied to every build
BASE_FLAGS: list[str] = [
    "-std=c++20",
    "-fno-exceptions",
    "-fno-rtti",
    "-Wall",
    "-Wextra",
    "-Wno-unused-parameter",   # Chess engine stubs often have unused params
]

# Chess-specific hardware flags — unlocks POPCNT, TZCNT, BMI1/2
CHESS_FLAGS: list[str] = [
    "-mpopcnt",
    "-mbmi",
    "-mbmi2",
]

# Optimization level flag sets
OPT_FLAGS: dict[str, list[str]] = {
    "O0": ["-O0"],                             # No optimization — debug builds
    "O1": ["-O1"],                             # Light optimization
    "O2": ["-O2"],                             # Standard release
    "O3": ["-O3", "-march=native"],            # Maximum — default for FastPy
    "Os": ["-Os"],                             # Size-optimized
}

DEFAULT_OPT = "O3"


# =============================================================================
# COMPILE RESULT
# =============================================================================

@dataclass
class CompileResult:
    """The outcome of a single compilation attempt."""
    ok:          bool
    binary_path: Optional[str]   # Set on success
    cpp_path:    str              # Path to the written .cpp file
    command:     list[str]        # Full compiler command that was run
    stdout:      str = ""
    stderr:      str = ""
    compiler:    str = ""

    def summary(self) -> str:
        """Return a one-line human-readable result."""
        if self.ok:
            return (
                f"✅  Compiled successfully → {self.binary_path}\n"
                f"    Compiler: {self.compiler}\n"
                f"    Command:  {' '.join(self.command)}"
            )
        return (
            f"❌  Compilation failed\n"
            f"    Compiler: {self.compiler}\n"
            f"    Command:  {' '.join(self.command)}\n"
            f"    Stderr:\n{self._indent(self.stderr)}"
        )

    @staticmethod
    def _indent(text: str, prefix: str = "      ") -> str:
        return "\n".join(prefix + line for line in text.splitlines())


# =============================================================================
# COMPILER DETECTION
# =============================================================================

class CompilerNotFoundError(Exception):
    """Raised when neither GCC nor Clang is available on the system."""
    pass


def find_compiler(prefer: Optional[str] = None) -> str:
    """
    Find an available C++ compiler on the system PATH.

    Search order: prefer → clang++ → g++ → c++

    Args:
        prefer: "clang++" or "g++" to override the default search order.

    Returns:
        The name of the available compiler (e.g. "clang++").

    Raises:
        CompilerNotFoundError if no compiler is found.
    """
    candidates = ["clang++", "g++", "c++"]

    if prefer:
        candidates = [prefer] + [c for c in candidates if c != prefer]

    for compiler in candidates:
        if shutil.which(compiler) is not None:
            return compiler

    raise CompilerNotFoundError(
        "No C++ compiler found on PATH. FastPy requires GCC or Clang.\n"
        "  Install on Ubuntu/Debian:  sudo apt install build-essential\n"
        "  Install on macOS:          xcode-select --install\n"
        "  Install Clang:             sudo apt install clang"
    )


def compiler_version(compiler: str) -> str:
    """Return the compiler version string, or 'unknown' on failure."""
    try:
        result = subprocess.run(
            [compiler, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.splitlines()[0] if result.stdout else "unknown"
    except Exception:
        return "unknown"


# =============================================================================
# CORE COMPILE FUNCTION
# =============================================================================

def compile_cpp(
    cpp_source: str,
    output_path: str,
    opt_level:   str = DEFAULT_OPT,
    compiler:    Optional[str] = None,
    extra_flags: Optional[list[str]] = None,
    keep_cpp:    bool = False,
) -> CompileResult:
    """
    Write C++ source to disk and compile it to a native binary.

    Args:
        cpp_source:  The C++ source code string from emitter.emit_module().
        output_path: Path for the output binary (e.g. "engine" or "engine.exe").
        opt_level:   One of "O0", "O1", "O2", "O3", "Os". Default: "O3".
        compiler:    Force a specific compiler ("clang++" or "g++").
                     Auto-detected if None.
        extra_flags: Additional compiler flags to append.
        keep_cpp:    If True, keep the temporary .cpp file after compilation.
                     Useful for debugging the emitter output.

    Returns:
        CompileResult with .ok, .binary_path, .stderr, .command, etc.
    """
    # Resolve output path to absolute
    output_path = str(Path(output_path).resolve())

    # Find compiler
    try:
        found_compiler = find_compiler(prefer=compiler)
    except CompilerNotFoundError as e:
        return CompileResult(
            ok=False,
            binary_path=None,
            cpp_path="",
            command=[],
            stderr=str(e),
        )

    # Write C++ source to a temp file
    cpp_fd, cpp_path = tempfile.mkstemp(suffix=".cpp", prefix="fastpy_")
    try:
        with os.fdopen(cpp_fd, "w", encoding="utf-8") as f:
            f.write(cpp_source)

        # Build compiler command
        opt_flags = OPT_FLAGS.get(opt_level, OPT_FLAGS[DEFAULT_OPT])
        command   = (
            [found_compiler]
            + BASE_FLAGS
            + CHESS_FLAGS
            + opt_flags
            + (extra_flags or [])
            + [cpp_path, "-o", output_path]
        )

        # Run compiler
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,
        )

        success = proc.returncode == 0
        return CompileResult(
            ok=success,
            binary_path=output_path if success else None,
            cpp_path=cpp_path,
            command=command,
            stdout=proc.stdout,
            stderr=proc.stderr,
            compiler=found_compiler,
        )

    except subprocess.TimeoutExpired:
        return CompileResult(
            ok=False,
            binary_path=None,
            cpp_path=cpp_path,
            command=command if 'command' in dir() else [],
            stderr="Compilation timed out after 120 seconds.",
            compiler=found_compiler,
        )

    except Exception as e:
        return CompileResult(
            ok=False,
            binary_path=None,
            cpp_path=cpp_path,
            command=[],
            stderr=f"Unexpected error during compilation: {e}",
        )

    finally:
        # Clean up temp .cpp file unless keep_cpp was requested
        if not keep_cpp and os.path.exists(cpp_path):
            try:
                os.unlink(cpp_path)
            except OSError:
                pass


# =============================================================================
# CONVENIENCE WRAPPERS
# =============================================================================

def compile_file(
    source_file: str,
    output_path: Optional[str] = None,
    opt_level:   str = DEFAULT_OPT,
    compiler:    Optional[str] = None,
) -> CompileResult:
    """
    Read a .cpp file from disk and compile it.

    Convenience wrapper for cases where the C++ was written to disk
    by an external tool rather than generated in-memory by FastPy.

    Args:
        source_file: Path to an existing .cpp file.
        output_path: Output binary path. Defaults to source filename minus .cpp
        opt_level:   Optimization level. Default: "O3".
        compiler:    Preferred compiler. Auto-detected if None.
    """
    source_path = Path(source_file)
    if not source_path.exists():
        return CompileResult(
            ok=False,
            binary_path=None,
            cpp_path=str(source_path),
            command=[],
            stderr=f"Source file not found: {source_file}",
        )

    if output_path is None:
        output_path = str(source_path.with_suffix(""))

    cpp_source = source_path.read_text(encoding="utf-8")
    return compile_cpp(
        cpp_source=cpp_source,
        output_path=output_path,
        opt_level=opt_level,
        compiler=compiler,
        keep_cpp=True,   # File already on disk — don't delete it
    )

"""
FastPy Test Fixtures and Helpers
=================================
Shared utilities used across all test modules.
Run the full suite from the repo root:

    pytest

Author: Gokul Chandar
Project: FastPy
"""

import pytest
import sys
import os

# Ensure the repo root is on the path so `from core.xxx import` works
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.parser      import parse_source, IRModule
from core.type_system  import check_module, TypeRegistry, TypeCheckResult
from core.emitter      import emit_module


# =============================================================================
# HELPER FUNCTIONS
# Importable by all test modules via `from conftest import emit_from_source`
# =============================================================================

def emit_from_source(source: str) -> str:
    """
    Full pipeline: Python source string → C++ string.
    Convenience wrapper used by emitter and intrinsics tests.
    """
    ir     = parse_source(source)
    result = check_module(ir)
    return emit_module(ir, result.registry)


def check_from_source(source: str) -> TypeCheckResult:
    """
    Parse + type-check a source string. Returns the TypeCheckResult.
    """
    ir = parse_source(source)
    return check_module(ir)


# =============================================================================
# COMMON SOURCE SNIPPETS
# Reusable source blocks shared between tests.
# =============================================================================

TYPE_ALIASES = """\
uint64 = int
int32  = int
bool8  = bool
"""

MINIMAL_FUNCTION = TYPE_ALIASES + """\
def identity(x: int32) -> int32:
    return x
"""

MINIMAL_CLASS = TYPE_ALIASES + """\
class Point:
    def __init__(self):
        self.x: int32 = 0
        self.y: int32 = 0
"""

POPCOUNT_SOURCE = TYPE_ALIASES + """\
def popcount(board: uint64) -> int32:
    return bin(board).count("1")
"""

TZCNT_SOURCE = TYPE_ALIASES + """\
def lsb(board: uint64) -> int32:
    return (board & -board).bit_length() - 1
"""


# =============================================================================
# PYTEST FIXTURES
# =============================================================================

@pytest.fixture
def type_aliases_ir():
    """IRModule built from the three standard type aliases."""
    return parse_source(TYPE_ALIASES)


@pytest.fixture
def minimal_function_ir():
    """IRModule with one typed function."""
    return parse_source(MINIMAL_FUNCTION)


@pytest.fixture
def registry() -> TypeRegistry:
    """A populated TypeRegistry built from the standard type aliases."""
    ir     = parse_source(TYPE_ALIASES)
    result = check_module(ir)
    return result.registry

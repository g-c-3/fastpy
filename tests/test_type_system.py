"""
Tests for core/type_system.py
==============================
Covers: type resolution, alias registration, the uint64 bug fix,
        array types, Final[] stripping, validation errors.
"""

import pytest
from core.parser      import parse_source
from core.type_system  import check_module, TypeRegistry, TypeCheckError
from conftest import TYPE_ALIASES, check_from_source


# =============================================================================
# TYPE REGISTRY — RESOLUTION
# =============================================================================

class TestTypeResolution:

    def test_uint64_resolves_to_uint64_t(self, registry):
        """
        Critical regression test.
        uint64 = int must NOT inherit int's int32_t mapping.
        The ground-truth table must win over the Python base type.
        """
        assert registry.resolve("uint64") == "uint64_t"

    def test_int32_resolves_to_int32_t(self, registry):
        assert registry.resolve("int32") == "int32_t"

    def test_bool8_resolves_to_bool(self, registry):
        assert registry.resolve("bool8") == "bool"

    def test_none_resolves_to_void(self, registry):
        assert registry.resolve("None") == "void"

    def test_int_resolves_to_int32_t(self, registry):
        assert registry.resolve("int") == "int32_t"

    def test_bool_resolves_to_bool(self, registry):
        assert registry.resolve("bool") == "bool"

    def test_final_wrapper_stripped(self, registry):
        assert registry.resolve("Final[uint64]") == "uint64_t"

    def test_final_int32_stripped(self, registry):
        assert registry.resolve("Final[int32]") == "int32_t"

    def test_struct_name_passes_through(self, registry):
        """Unknown PascalCase names pass through as-is — they are struct names."""
        assert registry.resolve("BoardState") == "BoardState"

    def test_array_base_type_stripped(self, registry):
        """uint64[218] → resolve base only → uint64_t."""
        assert registry.resolve("uint64[218]") == "uint64_t"

    def test_unknown_type_passes_through(self, registry):
        """Unknown lowercase names pass through — emitter will flag them."""
        assert registry.resolve("unknown_xyz") == "unknown_xyz"


# =============================================================================
# TYPE REGISTRY — ARRAY RESOLUTION
# =============================================================================

class TestArrayResolution:

    def test_array_element_type(self, registry):
        cpp_type, _ = registry.resolve_array("uint64[218]")
        assert cpp_type == "uint64_t"

    def test_array_size(self, registry):
        _, size = registry.resolve_array("uint64[218]")
        assert size == 218

    def test_int32_array(self, registry):
        cpp_type, size = registry.resolve_array("int32[64]")
        assert cpp_type == "int32_t"
        assert size == 64

    def test_non_array_type_returns_zero_size(self, registry):
        _, size = registry.resolve_array("uint64")
        assert size == 0

    def test_non_array_type_returns_correct_type(self, registry):
        cpp_type, _ = registry.resolve_array("uint64")
        assert cpp_type == "uint64_t"


# =============================================================================
# TYPE REGISTRY — is_known
# =============================================================================

class TestIsKnown:

    def test_uint64_is_known(self, registry):
        assert registry.is_known("uint64") is True

    def test_int32_is_known(self, registry):
        assert registry.is_known("int32") is True

    def test_unknown_string_is_not_known(self, registry):
        assert registry.is_known("unknown") is False

    def test_empty_string_is_not_known(self, registry):
        assert registry.is_known("") is False

    def test_struct_name_is_known(self, registry):
        """PascalCase names are treated as struct names — always known."""
        assert registry.is_known("BoardState") is True

    def test_final_uint64_is_known(self, registry):
        assert registry.is_known("Final[uint64]") is True

    def test_array_type_is_known(self, registry):
        assert registry.is_known("uint64[218]") is True


# =============================================================================
# ALIAS REGISTRATION — the uint64 bug
# =============================================================================

class TestAliasRegistration:

    def test_alias_registration_does_not_overwrite_ground_truth(self):
        """
        Registering `uint64 = int` must not overwrite uint64 → uint64_t
        with int → int32_t in the registry.
        """
        ir     = parse_source("uint64 = int")
        result = check_module(ir)
        assert result.registry.resolve("uint64") == "uint64_t"

    def test_all_three_aliases_resolve_correctly(self):
        ir     = parse_source(TYPE_ALIASES)
        result = check_module(ir)
        reg    = result.registry
        assert reg.resolve("uint64") == "uint64_t"
        assert reg.resolve("int32")  == "int32_t"
        assert reg.resolve("bool8")  == "bool"


# =============================================================================
# TYPE CHECK — PASS CASES
# =============================================================================

class TestTypeCheckPasses:

    def test_fully_typed_function_passes(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    return x"
        result = check_from_source(src)
        assert result.ok

    def test_typed_local_variable_passes(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    y: int32 = 0\n    return y"
        result = check_from_source(src)
        assert result.ok

    def test_array_annotation_passes(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    moves: uint64[218]\n    return x"
        result = check_from_source(src)
        assert result.ok

    def test_struct_passthrough_passes(self):
        src = TYPE_ALIASES + "def f(board: BoardState) -> int32:\n    return 0"
        result = check_from_source(src)
        assert result.ok

    def test_none_return_type_passes(self):
        src = TYPE_ALIASES + "def f(x: int32) -> None:\n    return"
        result = check_from_source(src)
        assert result.ok

    def test_reassignment_to_declared_var_passes(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    y: int32 = 0\n    y = x\n    return y"
        result = check_from_source(src)
        assert result.ok

    def test_simple_engine_zero_errors(self):
        """The example engine must always pass with zero type errors."""
        import os
        engine_path = os.path.join(
            os.path.dirname(__file__), "..", "examples", "simple_engine.py"
        )
        from core.parser import parse_file
        ir     = parse_file(engine_path)
        result = check_module(ir)
        assert result.ok, result.report()


# =============================================================================
# TYPE CHECK — FAILURE CASES
# =============================================================================

class TestTypeCheckFailures:

    def test_missing_param_type_is_error(self):
        src = TYPE_ALIASES + "def f(x) -> int32:\n    return 0"
        result = check_from_source(src)
        assert not result.ok
        assert any("param 'x'" in str(e) for e in result.errors)

    def test_missing_return_type_is_error(self):
        src = TYPE_ALIASES + "def f(x: int32):\n    return x"
        result = check_from_source(src)
        assert not result.ok
        assert any("return type" in str(e) for e in result.errors)

    def test_untyped_first_variable_is_error(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    y = 0\n    return y"
        result = check_from_source(src)
        assert not result.ok
        assert any("'y'" in str(e) for e in result.errors)

    def test_zero_errors_on_correct_code(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    y: int32 = 0\n    return y"
        result = check_from_source(src)
        assert len(result.errors) == 0

    def test_report_ok_message(self):
        src = TYPE_ALIASES + "def f(x: int32) -> int32:\n    return x"
        result = check_from_source(src)
        assert "zero errors" in result.report().lower()

    def test_report_failure_message(self):
        src = TYPE_ALIASES + "def f(x) -> int32:\n    return 0"
        result = check_from_source(src)
        assert "error" in result.report().lower()

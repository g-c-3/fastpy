# FastPy — Session Log

Append-only. One entry per session. Most recent at top.

---

## Session 3 — 2026-06-27 (morning)

**Focus:** Complete emitter fixes, variable hoisting, fastpy-engine/engine.py Phase 1 full build.

**Completed:**
- Parser: subscript assignment targets (`moves[count] = value`, `moves[0] = 99`) — done
- Type checker: subscript writes to declared arrays pass cleanly — done
- Emitter fix 1: array params (`uint64[218]`) emit as `uint64_t* moves` via `_cpp_param()` helper
- Emitter fix 2: variable hoisting — `_collect_typed_scalars()` pre-declares all scalar locals at C++ function scope before the body, matching Python's flat scoping model. Fixes "not declared in this scope" errors in sibling while blocks.
- Emitter fix 3: bitwise right-operand explicit parens `(a & (b-1))` — silences `-Wparentheses`
- `_fn_declared` set tracks hoisted vars so annotated re-assignments emit as plain C++ assignments
- `double` → `double_push` rename in engine.py (C++ keyword conflict)
- Unused `move` variable removed from `alpha_beta` (Phase 1 placeholder)
- `main() -> int32` stub added to engine.py for linker
- 8 emitter tests updated/added (5 paren format, 3 array decay/hoisting) → **168/168 passing**
- `fastpy check engine.py` → zero errors ✅
- `fastpy build engine.py --optimize=O3` → **compiles and runs** ✅
- C++ output verified: `__builtin_popcountll`, `__builtin_ctzll`, `uint64_t* moves`, `uint64_t moves[218] = {}`

**Files changed:**
- `core/parser.py` — `_resolve_target` subscript support
- `core/type_system.py` — `_check_assign` subscript handling
- `core/emitter.py` — `_collect_typed_scalars`, `_cpp_param`, hoisting in `_emit_function`, `_fn_declared`, `_emit_binop` parens, `_emit_assign` scope fix
- `core/__init__.py` — NEW
- `pyproject.toml` — NEW
- `fastpy_main.py` — NEW
- `.github/workflows/ci.yml` — updated
- `tests/test_parser.py` — 4 new subscript tests
- `tests/test_type_system.py` — 3 new subscript tests
- `tests/test_emitter.py` — 8 tests updated/added
- `fastpy-engine/engine.py` — NEW (Phase 1 complete, compiles)

---

## Session 2 — 2026-06-26 (afternoon)

**Focus:** Test suite, bug fixes, project documentation infrastructure.

**Completed:**
- Wrote full 155-test suite across 4 test files + conftest + pytest.ini
- Fixed `uint64 = int` bug in `parser._try_type_alias` — ground-truth name checked first
- Fixed TZCNT partial-fire bug — rewrote `_match_tzcnt` as full inline pattern match, removed `_match_bit_length` from `_match_call`
- Fixed `test_unsupported_expression_raises` — switched from string literal (now valid) to lambda
- All 155 tests passing in 1.82s
- Wrote `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`
- Created `docs/` directory with all 5 documentation files
- Wrote Project Instructions for Claude Project

**Files changed:**
- `core/parser.py` — `_try_type_alias` fix + `IRCall.receiver` field
- `core/intrinsics.py` — TZCNT full inline rewrite
- `tests/conftest.py`, `test_parser.py`, `test_type_system.py`, `test_emitter.py`, `test_intrinsics.py` — new
- `pytest.ini` — new
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` — new
- `docs/` — all 5 files new

**Known issues carried forward:**
- `python -m pytest tests/ -v` not yet added to `ci.yml`
- `pyproject.toml` not written
- `fastpy-engine/engine.py` not started

---

## Session 1 — 2026-06-26 (morning)

**Focus:** Full Phase 1 transpiler build from scratch.

**Completed:**
- Designed complete FastPy architecture (6 modules)
- Wrote all 6 core modules: `parser.py`, `type_system.py`, `emitter.py`, `intrinsics.py`, `toolchain.py`, `main.py`
- Wrote `examples/simple_engine.py` — FastPy-dialect chess engine, zero type errors
- Fixed `simple_engine.py` — 11 type errors resolved (`moves: list = []`, pre-branch declarations, `-> tuple` return type, `best_move: uint64 = 0`)
- Set up CI workflow — green on first commit
- Wrote `fastpy` README (with FastPy-Engine section), `fastpy-engine` README, GPL v3 LICENSE
- Established Claude Project with both GitHub repos connected

**Key decisions made:**
- `IRCall.receiver` field to preserve `bin(board)` for POPCNT matching
- Ground-truth C++ type table in type_system to fix `uint64 = int → uint64_t`
- Intrinsics as a hook inside emitter, not a pre-pass
- `from __future__ import annotations` in `simple_engine.py` for Python runtime compatibility
- `list`/`tuple` accepted by type checker with TODO placeholder in C++ output

**Files created (all new):**
- `core/parser.py`, `core/type_system.py`, `core/emitter.py`, `core/intrinsics.py`, `core/toolchain.py`
- `main.py`
- `examples/simple_engine.py`
- `.github/workflows/ci.yml`
- `README.md`, `fastpy-engine/README.md`, `fastpy-engine/LICENSE`

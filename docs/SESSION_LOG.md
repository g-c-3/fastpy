# FastPy — Session Log

Append-only. One entry per session. Most recent at top.

---

## Session 7 — Phase 4: Search Improvements
**Date:** 2026-06-29
**Status:** COMPLETE ✅

### Completed
- `piece_at_square(sq, board) -> int32` — returns piece value for MVV-LVA
- `mvv_lva(move, board) -> int32` — victim*10 - attacker capture priority score
- `sort_moves(moves, count, board) -> None` — in-place selection sort (O(n²), n≤218)
- `generate_captures(board, moves, count) -> int32` — legal captures only (for qsearch)
- `quiescence(board, alpha, beta) -> int32` — stand-pat + capture search to avoid horizon effect
- Updated `alpha_beta` — depth==0 now calls `quiescence()` instead of `evaluate()`; `sort_moves()` before search loop
- `run.py` full rewrite — Phase 4 additions:
  - `_generate_captures_py()` Python wrapper
  - `_quiescence_py()` Python wrapper
  - `_alpha_beta_py()` updated: calls `_quiescence_py` at depth 0, MVV-LVA move ordering
  - `_iterative_deepening_py(board, max_time_ms, max_depth)` — IDS with info line output
  - `uci_loop()` updated: handles `go movetime N`, `go wtime N btime N`, `go infinite`, outputs info depth lines
- Fixed `tests/test_move_gen.py` path bug — `os.path.dirname(__file__)` pointed to tests/ not repo root
- Fixed `tests/test_uci.py` ENGINE_CMD — was `engine.py` (no UCI loop after D-23 split); updated to `run.py`
- `tests/test_phase4.py` NEW — 40 tests, all passing
- **117/117 tests passing** (56 move_gen + 21 uci + 40 phase4)
- `fastpy check engine.py` → zero errors ✅
- `fastpy emit` → 1206 lines C++, compiles clean with g++ -O3 -march=native ✅

### Key Decisions
- D-24: generate_captures uses generate_all_moves + filter (reuse existing logic, correct by construction)
- D-25: quiescence() and generate_captures() are compile-only; Python tests use run.py wrappers (same pattern as alpha_beta, generate_legal_moves)

### Files changed
- fastpy-engine/engine.py (1408 → 1549 lines, +141 lines)
- fastpy-engine/run.py (275 → 488 lines, full rewrite for Phase 4)
- fastpy-engine/tests/test_phase4.py (NEW, 410 lines, 40 tests)
- fastpy-engine/tests/test_move_gen.py (path fix only)
- fastpy-engine/tests/test_uci.py (ENGINE_CMD fix only)

### Next
Phase 4 continued: Piece-Square Tables (PST), null move pruning, transposition table

---

## Session 6 — Phase 3: Complete Move Generation
**Date:** 2026-06-28
**Status:** COMPLETE ✅

### Completed
- 8 ray generators (ray_north/south/east/west + 4 diagonals)
- knight_attack_mask, king_attack_mask (shared by move gen + check detection)
- generate_bishops, generate_rooks, generate_queens (ray-fill, zero allocation)
- is_sq_attacked(sq, board, by_black) — reverse attack tracing
- is_in_check(board) — post-make_move legality check
- generate_castling — full castling with rights + path + attack checks
- Updated generate_all_moves — all piece types + castling
- Updated make_move — castling rook movement + castling rights updates (positive masks)
- generate_legal_moves — pseudo-legal → filter by is_in_check
- perft(board, depth) — correctness benchmark function
- Updated alpha_beta + find_best_move → use generate_legal_moves
- 56 tests in test_move_gen.py — 56/56 passing
- Perft(1-4) verified: 20, 400, 8902, 197281 ✅
- Perft(5) = 4,865,609 verified via compiled binary (-O3 -march=native, 0.25s)
  Method: fastpy emit → patch stub main() → g++ -O3 -march=native → run

- Split engine.py / run.py (D-23): engine.py now 1408 lines (dialect only),
  run.py 275 lines (Python UCI runner). fastpy check + build + UCI all verified.

### Key Decisions
- D-21: Python make_move copy semantics (see DECISIONS.md)
- D-22: Castling rights use positive masks not bitwise NOT

### Files changed
- fastpy-engine/engine.py (600 → 1602 lines)
- fastpy-engine/tests/test_move_gen.py (new, 675 lines)

### Next
- Phase 4: Perft(5) from binary (4,865,609), UCI position parsing fixes,
  move ordering (MVV-LVA), quiescence search

---

## Session 5 — 2026-06-28

**Focus:** Sprint 8 — UCI Protocol.

**Completed:**
- `engine.py`: Fixed `knight: uint64 = 1 << from_sq` → `BIT_ONE << from_sq` in `generate_knights`. The `1` literal is a 32-bit int in C++; `BIT_ONE` (constexpr uint64_t) ensures correct 64-bit shift for all 64 squares.
- `engine.py`: Added complete UCI protocol in `if __name__ == '__main__':` block (FastPy silently skips this via `_visit_top_level`). Commands: `uci`, `isready`, `ucinewgame`, `position startpos [moves ...]`, `go [depth N]`, `stop`, `setoption`, `debug`, `quit`.
- `engine.py`: Added `_alpha_beta_py` and `_find_best_move_py` Python-mode wrappers inside the `__main__` block. These mirror the compiled search functions but use Python lists instead of `uint64[218]` stack arrays (which are unbound in Python mode). UCI loop uses these wrappers.
- `engine.py`: Added `_sq_to_str`, `_move_to_uci`, `_parse_sq`, `_parse_uci_move`, `_apply_position`, `_uci_loop` — all Python-only UCI helpers.
- `fastpy-engine/tests/test_uci.py` — NEW: 21 UCI integration tests (subprocess-based). Tests handshake, position parsing, search output format, robustness. **21/21 passing in 0.71s**.
- `fastpy check engine.py` → zero errors ✅
- `fastpy emit engine.py` → 663 lines C++ ✅
- `python engine.py` works as a full UCI engine — tested with Arena/Cutechess-style command sequences.

**Architectural decision recorded:** UCI loop lives in `if __name__ == '__main__':` (D-19 below). Python search wrappers needed because `moves: uint64[218]` bare declarations are unbound in Python.

**Files changed:**
- `fastpy-engine/engine.py` — UCI block added, knight BIT_ONE fix
- `fastpy-engine/tests/test_uci.py` — NEW

---

## Session 4 — 2026-06-27 

**Focus:** `make_move()`, two transpiler fixes, alpha-beta wired up.

**Completed:**
- Emitter: `_HOISTABLE_TYPES` set — hoisting now skips struct types (e.g. `BoardState`). `BoardState new_board = 0` is invalid C++; structs are declared inline where first used.
- Type checker: dotted targets (`board.white_pawns = ...`) now exempt from first-use annotation requirement. `"." not in target` replaces `not target.startswith("self.")` — covers both `self.field` and `param.field` struct writes.
- 3 new type_system tests → **171/171 passing**
- `engine.py`: Added `BIT_ONE: Final[uint64] = 1` constant — ensures `BIT_ONE << sq` emits as `uint64_t` shift (plain `1 << sq` is 32-bit int in C++, UB for sq > 30)
- `engine.py`: `make_move(board, move) -> BoardState` — full implementation. Value-copy semantics: takes BoardState by value, modifies the local copy, returns it. Handles: captures (all 6 piece types), en passant, double-push ep square update, promotions (queen/knight/bishop), side-to-move flip.
- `alpha_beta()`: wired up with `new_board: BoardState = make_move(board, moves[i])` — real recursive search, no more static evaluation placeholder.
- `fastpy check engine.py` → zero errors ✅
- `fastpy build engine.py --optimize=O3` → **662 lines C++, compiles clean** ✅

**Key C++ output verified:**

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

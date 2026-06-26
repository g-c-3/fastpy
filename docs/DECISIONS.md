# FastPy — Key Decisions

Every significant decision recorded here with its rationale.
When a decision changes, the old entry stays (struck through) and the new one is added below it with a date.

---

## Project-Level Decisions

### D-01: Chess engines only — not general Python
**Decision:** FastPy targets chess engine development exclusively. Not a general Python transpiler.  
**Rationale:** General Python transpilation is an unsolved research problem (Cython, Numba, etc. all have major limitations). Narrowing to chess engines means we can make hard guarantees: fixed-size arrays, no GC, bitboard-centric types, hardware intrinsics for POPCNT/TZCNT. The narrow scope is the product's entire value proposition.

### D-02: MIT for fastpy, GPL v3 for fastpy-engine
**Decision:** The transpiler tool (`fastpy`) is MIT. The chess engine (`fastpy-engine`) is GPL v3.  
**Rationale:** MIT on the tool lets anyone — including commercial projects — use and embed FastPy freely. GPL v3 on the engine is consistent with the open-source chess engine community standard (Stockfish and most competitive engines are GPL). The two-repo split cleanly separates these licenses.

### D-03: Pure Python — zero external dependencies
**Decision:** FastPy uses only the Python standard library.  
**Rationale:** Zero install friction. `git clone` + `python main.py` works immediately. No pip, no venv, no version conflicts. Chess engine developers should be able to contribute without a complex Python environment.

### D-04: Two separate repos
**Decision:** `g-c-3/fastpy` (the tool) and `g-c-3/fastpy-engine` (the engine) are separate repositories.  
**Rationale:** Different licenses. Different contributor audiences (compiler developers vs chess engine developers). Different release cadences. The README of each links to the other.

---

## Architecture Decisions

### D-05: Dataclass IR nodes — not AST subclasses
**Decision:** All IR nodes are `@dataclass` instances, not subclasses of `ast.AST`.  
**Rationale:** The Python AST is complex, mutable, and has many fields irrelevant to FastPy. Clean dataclasses are simpler to inspect, test, and extend. The emitter and type system can pattern-match on `type(node).__name__` without importing the `ast` module.

### D-06: One C++ construct per IR node — no analysis in emitter
**Decision:** The emitter is a pure tree-walk. Every IR node maps to exactly one C++ string. Zero analysis happens in the emitter.  
**Rationale:** Keeps the emitter predictable and testable. Analysis belongs in the type system. Optimization belongs in the compiler (`-O3`). The emitter's job is purely structural translation.

### D-07: Intrinsics as a hook — not a pre-pass
**Decision:** `intrinsics.py` is wired as a hook inside `emitter._emit_expr()`, not as an IR transformation pre-pass.  
**Rationale:** A pre-pass would require a separate IR traversal and potentially mutating the tree. The hook is simpler: called for every expression, returns `str | None`. The emitter falls back to baseline C++ if `None` is returned. This keeps intrinsics self-contained.

### D-08: IRCall.receiver field
**Decision:** `IRCall` has an optional `receiver: Any = None` field that stores the object expression for method calls on non-name objects.  
**Rationale:** Without this, `bin(board).count("1")` loses the `bin(board)` part during parsing. The intrinsic mapper needs the full chain to generate `__builtin_popcountll(board)`. The receiver is set only when the call target is an attribute of a non-name expression (e.g. the result of another call).

### D-09: Ground-truth C++ type table in type_system.py
**Decision:** `type_system.py` maintains `_CPP_TYPE_TABLE` as the authoritative mapping of FastPy names to C++ types. The parser's `BUILTIN_TYPE_MAP` is secondary.  
**Rationale:** The parser encounters `uint64 = int` and naturally maps it through `int → int32_t`. Without a ground-truth override, `uint64` would resolve to `int32_t` — wrong. The ground-truth table is checked first by alias name, so `uint64` always resolves to `uint64_t` regardless of what Python base type it was aliased from.

### D-10: TZCNT as a full inline pattern match
**Decision:** The TZCNT pattern `(x & -x).bit_length() - 1` is matched entirely inside `_match_tzcnt()`. There is no intermediate `_match_bit_length()` called from `_match_call()`.  
**Rationale:** The original two-stage design (match `bit_length()` call independently, then collapse `- 1`) caused TZCNT to fire for `(x & -x).bit_length() - 2` — the inner call matched and produced `__builtin_ctzll(x) + 1`, which leaked into the output. The full inline approach only fires when all conditions are simultaneously satisfied.

### D-11: from __future__ import annotations in simple_engine.py
**Decision:** `simple_engine.py` uses `from __future__ import annotations` at the top.  
**Rationale:** Without it, `moves: uint64[218]` raises `TypeError: 'int' object is not subscriptable` at Python runtime (since `uint64 = int`). With PEP 563 lazy annotations, the annotation is stored as a string and never evaluated. FastPy's parser reads the raw AST (before Python evaluates), so it still sees the correct annotation structure.

### D-12: list and tuple allowed as valid types in type checker
**Decision:** `"list"` and `"tuple"` are in `_CPP_TYPE_TABLE` with comment-placeholder C++ values. The type checker accepts them without error.  
**Rationale:** `simple_engine.py` uses Python `list` for move arrays (Python-mode compatibility). The checker accepting `list` lets the example file pass with zero errors while the emitter still outputs a clear TODO comment indicating the upgrade path to `uint64[218]`. Error on `list` would block running `fastpy check` on the example — the wrong failure mode.

### D-13: emit_module() auto-wires intrinsics
**Decision:** `emit_module()` automatically imports and wires `IntrinsicMapper` if `intrinsics.py` is available. Pass `intrinsic_hook=False` to disable.  
**Rationale:** Callers should not need to know that intrinsics exist. The default experience is "compile with maximum hardware acceleration". Explicit opt-out is available for debugging or testing baseline C++ output.

---

## Decisions Pending / Open Questions

### DP-01: Move encoding in fastpy-engine
**Options:**
- A) Pack `from_sq | (to_sq << 6)` into a single `uint64` — simple, one array
- B) Separate `int32[218]` arrays for from/to squares — readable but two arrays
- C) Full move struct (from, to, piece, flags) packed into 32 bits — extensible

**Current lean:** Option A for Phase 1 simplicity. Revisit for Phase 3 when promotions and special moves need flags.

### DP-02: Return type for find_best_move
**Problem:** `find_best_move` currently returns a Python `tuple` (best_move, best_score). C++ cannot return a tuple from a function without a struct.  
**Options:** Return packed `uint64`, use output parameters, return a result struct.  
**Status:** Deferred until `fastpy-engine/engine.py` is written.

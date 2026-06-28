# FastPy — Project Context

## Purpose

FastPy is a **speed-first Python-to-C++ transpiler** built exclusively for chess engines.
The goal: write a world-class chess engine in clean Python, compile it to bare-metal C++ with a single command, and run it at **100,000,000+ Nodes Per Second**.

Standard Python chess engines reach ~50,000 NPS. Stockfish exceeds 100,000,000 NPS.
FastPy bridges that 2000x gap without the developer ever touching C++.

```bash
fastpy build engine.py --optimize=O3
```

## Two Repos

| Repo | License | Purpose |
|---|---|---|
| `g-c-3/fastpy` | MIT | The transpiler tool — parser, type system, emitter, intrinsics, CLI |
| `g-c-3/fastpy-engine` | GPL v3 | The chess engine written in FastPy dialect — proof of concept |

## Current Status

**FastPy transpiler (g-c-3/fastpy):** Phase 1 complete. All 6 core modules built, 155 tests passing, CI green on Python 3.11 + 3.12.

**FastPy-Engine (g-c-3/fastpy-engine):** Phase 3 complete.
- All piece types: pawns, knights, bishops, rooks, queens, king
- Castling (rights tracking, path + attack checks)
- En passant, promotions
- Check detection (`is_sq_attacked`, `is_in_check`)
- Legal move filtering (`generate_legal_moves`)
- Perft(5) = 4,865,609 verified ✅ (0.25s compiled at -O3 -march=native)
- UCI protocol via `run.py`

## Tech Stack

- **Language:** Pure Python 3.11+ — zero external dependencies
- **IR:** Python `@dataclass` nodes — `IRModule`, `IRFunction`, `IRClass`, `IRCall`, etc.
- **AST reading:** Python built-in `ast` module
- **C++ target:** C++20 with `-O3 -march=native -mpopcnt -mbmi -mbmi2 -fno-exceptions -fno-rtti`
- **CI:** GitHub Actions — Python 3.11 + 3.12 matrix

## Folder Structure

```
fastpy/
├── main.py                        # CLI entry point (build/check/emit/intrinsics)
├── core/
│   ├── parser.py                  # ast → FastPy IR
│   ├── type_system.py             # validates types, builds TypeRegistry
│   ├── emitter.py                 # IR → C++ string
│   ├── intrinsics.py              # chess pattern → hardware instruction
│   └── toolchain.py               # GCC/Clang compiler bridge
├── examples/
│   └── simple_engine.py           # FastPy-dialect example — zero type errors
├── tests/
│   ├── conftest.py                # shared fixtures and helpers
│   ├── test_parser.py             # 46 tests
│   ├── test_type_system.py        # 38 tests
│   ├── test_emitter.py            # 43 tests
│   └── test_intrinsics.py         # 28 tests
├── docs/
│   ├── PROJECT_CONTEXT.md         # this file
│   ├── ARCHITECTURE.md            # pipeline and IR deep-dive
│   ├── ROADMAP.md                 # sprint-level task tracking
│   ├── DECISIONS.md               # why things are the way they are
│   └── SESSION_LOG.md             # append-only session history
├── .github/workflows/ci.yml       # CI pipeline
├── pytest.ini                     # testpaths + pythonpath
├── README.md
├── CONTRIBUTING.md
└── CODE_OF_CONDUCT.md

fastpy-engine/
├── engine.py                      # FastPy dialect only — compiled functions
├── run.py                         # Python UCI runner — from engine import *
├── tests/
│   ├── test_uci.py                # UCI protocol tests
│   └── test_move_gen.py           # Move generation + perft correctness
├── README.md
└── LICENSE                        # GPL v3
```

## The FastPy Speed Contract

Every function compiled by FastPy must follow three rules:

1. **Strict static typing** — every variable and parameter has an explicit type hint
2. **Zero dynamic allocation** — no `list.append()`, no `dict`, no heap inside loops; use `uint64[218]` fixed-size stack arrays
3. **No CPython runtime** — generated binary is standalone; no GC, no GIL, no interpreter

## Known Bugs / Limitations

- **`list`/`tuple` in C++:** `simple_engine.py` uses Python `list` for move arrays. The emitter outputs a comment placeholder. Upgrade path: `uint64[218]` in `fastpy-engine`.
- **Non-range `for` loops:** `for move in moves` emits a `/* TODO */` comment. Must use `for i in range(n)` with indexed access.
- **No multi-file compilation:** Single `.py` file only. Multi-module support is Phase 3.
- **No Windows support:** `toolchain.py` uses POSIX conventions. MSVC/MinGW not detected.
- **CI gap:** `python -m pytest tests/ -v` step is missing from `.github/workflows/ci.yml`. Must be added.

## Important Constraints

- FastPy is chess-engine-specific. Do not generalise to arbitrary Python.
- Every IR node maps to exactly one C++ construct. The emitter does zero analysis.
- The type system validates. The emitter trusts. Never mix these responsibilities.
- `simple_engine.py` must always pass `fastpy check` with zero errors and run correctly as plain Python.

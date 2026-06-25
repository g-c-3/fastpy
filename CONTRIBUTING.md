# Contributing to FastPy

Thank you for your interest in contributing to FastPy.  
FastPy is an early-stage open-source project and every contribution — code, tests, documentation, bug reports — directly shapes what it becomes.

---

## Before You Start

Please read [README.md](README.md) to understand the project vision and the **FastPy Speed Contract** (the three rules all compiled code must follow). Understanding why those rules exist will make your contributions much more effective.

All contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

---

## How To Contribute

### 1. Fork and clone

```bash
git clone https://github.com/YOUR_USERNAME/fastpy.git
cd fastpy
```

No external dependencies — FastPy is written in pure Python and uses only the standard library. Python 3.11 or higher is required.

### 2. Create a feature branch

```bash
git checkout -b feature/your-feature-name
```

Use a descriptive branch name:
- `feature/emitter-for-loops` — adding a new capability
- `fix/type-system-array-resolution` — fixing a bug
- `test/bitboard-intrinsics` — adding tests
- `docs/dialect-guide` — documentation

### 3. Make your changes

See [Project Architecture](#project-architecture) below for a map of the codebase.

Run the smoke test before submitting:

```bash
# Type-check the example engine
python main.py check examples/simple_engine.py

# Confirm it still runs as Python
python examples/simple_engine.py

# Confirm C++ emission works
python main.py emit examples/simple_engine.py -o /tmp/test_output.cpp
```

All three must pass with zero errors.

### 4. Submit a Pull Request

Open a PR against the `main` branch with:
- A clear title describing what changed
- A description of **why** you made the change
- Any relevant test output or generated C++ snippets

CI runs automatically on every PR. It must be green before merging.

---

## Project Architecture

```
fastpy/
├── main.py              # CLI entry point — wires all modules together
├── core/
│   ├── parser.py        # AST visitor → FastPy IR (Intermediate Representation)
│   ├── type_system.py   # Strict type enforcer + TypeRegistry
│   ├── emitter.py       # IR → raw C++ source code
│   ├── intrinsics.py    # Chess pattern → hardware instruction mapper
│   └── toolchain.py     # GCC/Clang compiler bridge
├── examples/
│   └── simple_engine.py # FastPy-dialect example chess engine
└── tests/               # Test suite (pytest)
```

**Module responsibilities:**

| Module | Input | Output | Does NOT do |
|---|---|---|---|
| `parser.py` | Python source file | IRModule | Type validation, C++ generation |
| `type_system.py` | IRModule | TypeRegistry + errors | C++ generation |
| `emitter.py` | IRModule + TypeRegistry | C++ string | Compilation, type checking |
| `intrinsics.py` | IR expression node | C++ string or None | Anything else |
| `toolchain.py` | C++ string + output path | Binary + result | IR processing |

Each module has exactly one job. Keep it that way.

---

## Where Help Is Needed

### Core Development

**`core/parser.py`**
- Support for `match` statements (Python 3.10+)
- Better error messages with source context (highlight the offending line)
- Support for typed function local variables without initial values

**`core/emitter.py`**
- Struct method `const` qualification inference
- Output parameter pattern for move list functions
- Proper `uint64[218]` → C-style array in all contexts

**`core/intrinsics.py`**
- BMI2 patterns: `PEXT`/`PDEP` for magic bitboard generation
- `__builtin_clzll` for most-significant-bit index
- Sliding piece attack patterns (Hyperbola Quintessence)

**`core/toolchain.py`**
- Windows support (MSVC / MinGW detection)
- Apple Silicon cross-compilation flags
- Compilation caching (avoid recompiling unchanged sources)

### Testing

- Perft test cases for move generator correctness
- Round-trip tests: Python source → C++ → compile → run → output matches Python output
- Benchmark suite: measure NPS of generated binaries across hardware
- Edge case tests for the type checker (missing annotations, unknown types, etc.)

### Documentation

- FastPy Dialect Guide: a complete reference for writing FastPy-compliant Python
- Tutorial: "Your first chess engine in FastPy"
- Contributor guide for chess engine developers unfamiliar with Python tooling

---

## Code Style

FastPy's own source code follows these conventions:

- **Type hints on all function signatures** — FastPy enforces types in user code, so we do too
- **Dataclasses for IR nodes** — all IR nodes in `parser.py` are `@dataclass`
- **One responsibility per module** — the module boundary table above is a hard rule
- **Descriptive variable names** — `cpp_type` not `t`, `source_file` not `f`
- **Docstrings on all public functions** — single-line for simple functions, full block for public API
- Line length: 100 characters

No formatter is enforced yet. Common sense is the standard.

---

## Reporting Bugs

Open a GitHub Issue with:
- The FastPy source file that caused the problem (or a minimal reproduction)
- The exact command you ran
- The full error output
- Your Python version (`python --version`) and OS

---

## Questions

For questions about architecture or the project direction, open a GitHub Discussion or contact the project creator directly via GitHub ([@g-c-3](https://github.com/g-c-3)).

# FastPy 🚀

> **Write chess engines in Python. Run them at C++ speeds.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Early Development](https://img.shields.io/badge/Status-Early%20Development-orange)]()
[![Contributions Welcome](https://img.shields.io/badge/Contributions-Welcome-brightgreen)]()

---

## What Is FastPy?

FastPy is a **speed-first Python-to-C++ transpiler** built exclusively for one purpose:

**To make it possible to write a world-class chess engine in Python and have it execute at bare-metal C++ speeds.**

Standard Python chess engines struggle to reach **50,000 Nodes Per Second (NPS)**.  
Stockfish, written in C++, screams past **100,000,000+ NPS**.

FastPy bridges that 2000x gap.

You write clean, readable Python. FastPy compiles it into raw, optimized C++ and hands you a native binary — without you ever touching C++ directly.

---

## The Problem FastPy Solves

Every Python chess engine developer faces the same wall:

```python
# You want to write this (clean, readable Python)
def get_attacks(board: uint64, piece: uint64) -> uint64:
    return (piece << 8) & (~board)
```

Python executes this beautifully — but far too slowly for serious chess.  
The only option today is to manually rewrite it in C++.

**FastPy eliminates that rewrite.**

It reads your Python, understands your intent, and generates the equivalent bare-metal C++ — including direct hardware CPU instruction mappings that even many C++ programmers miss.

---

## How It Works

```
Your Python File (engine.py)
        │
        ▼
[ FastPy Parser ]        ← Reads your code using Python's ast module
        │
        ▼
[ Type Enforcer ]        ← Validates all variables are strictly typed
        │
        ▼
[ C++ Emitter ]          ← Generates raw, zero-allocation C++ code
        │
        ▼
[ Hardware Mapper ]      ← Maps Python idioms to CPU assembly intrinsics
        │
        ▼
[ Compiler Bridge ]      ← Calls GCC/Clang with maximum optimization flags
        │
        ▼
Native Binary (engine)   ← Runs at 100,000,000+ NPS
```

**One command. That's all it takes:**

```bash
fastpy build engine.py --optimize=O3
```

---

## The FastPy Rules (Speed Contract)

To achieve C++ speeds, code compiled by FastPy must follow three strict rules.  
Think of these not as limitations, but as the **speed contract**:

### 1. Strict Static Typing
Every variable in performance-critical functions must have an explicit type hint:

```python
# ✅ FastPy accepts this
def count_pieces(board: uint64) -> int32:
    return bin(board).count("1")

# ❌ FastPy rejects this
def count_pieces(board):
    return bin(board).count("1")
```

### 2. Zero Dynamic Allocation
No dynamic lists, no dictionaries, no heap allocation inside compiled loops.  
Everything maps to fixed-size C-style arrays on the CPU stack:

```python
# ✅ FastPy accepts this
moves: uint64[218]   # Fixed-size array → stack allocated in C++

# ❌ FastPy rejects this
moves = []           # Dynamic list → heap allocated, GC paused
```

### 3. No CPython Runtime Dependencies
The generated C++ is completely standalone — no Python interpreter required at runtime.  
This eliminates garbage collection pauses and interpreter overhead entirely.

---

## Chess-Specific Hardware Optimizations

This is where FastPy becomes truly unique.

FastPy recognizes chess-specific Python patterns and replaces them with  
**single-clock-cycle CPU hardware instructions**:

| You Write in Python | FastPy Generates | CPU Instruction | Speed |
|---|---|---|---|
| `bin(board).count("1")` | `__builtin_popcountll(board)` | `POPCNT` | 1 clock cycle |
| `x & -x` (least significant bit) | `__builtin_ctzll(x)` | `TZCNT` | 1 clock cycle |
| Bitwise shifts `<<` `>>` | Direct register operations | `SHL` `SHR` | 1 clock cycle |

These optimizations alone can multiply engine speed by **10x to 50x** compared to  
equivalent C++ code that doesn't use hardware intrinsics.

---

## The Flagship Use Case: FastPy-Engine

The best proof of what FastPy can do is **FastPy-Engine** —  
a complete, competitive chess engine written entirely in FastPy dialect Python  
and compiled to native C++, targeting **1 Billion Nodes Per Second**.

FastPy-Engine is what FastPy was built for. It is the real-world demonstration  
that the speed contract works — that clean, readable Python can become  
a world-class chess engine with a single build command.

→ **[github.com/g-c-3/fastpy-engine](https://github.com/g-c-3/fastpy-engine)**

---

## Project Architecture

FastPy is written entirely in pure Python — making it accessible for any Python  
developer to read, understand, and contribute to.

```
fastpy/
├── main.py              # CLI entry point (~100 lines)
├── core/
│   ├── parser.py        # AST Structural Visitor (~300-800 lines)
│   ├── type_system.py   # Strict Type Enforcer (~200-500 lines)
│   ├── emitter.py       # Raw C++ Code Generator (~400-1200 lines)
│   ├── intrinsics.py    # Chess Hardware Mappings (~200-400 lines)
│   └── toolchain.py     # GCC/Clang Compiler Bridge (~150 lines)
├── tests/
│   ├── test_bitboards.py
│   ├── test_intrinsics.py
│   └── reference/       # Known-good C++ output files
├── examples/
│   └── simple_engine.py # Example FastPy-dialect chess engine
├── README.md
└── LICENSE
```

**Development Scale:**
- Phase 1 MVP: ~500–1,000 lines of Python
- Phase 2 Production Core: ~3,000–5,000 lines
- Phase 3 Mature Ecosystem: ~10,000+ lines

---

## Why Not Just Use Cython, Numba, or ComPy?

| Feature | Cython | Numba | ComPy | **FastPy** |
|---|---|---|---|---|
| Target | General Python | Math/Arrays | General C++ | **Chess engines** |
| Memory Model | GC-based | GC-based | Object wrappers | **Naked stack primitives** |
| Chess Intrinsics | ❌ | ❌ | ❌ | **✅ POPCNT, TZCNT, BMI2** |
| Zero-GC Guarantee | ❌ | ❌ | ❌ | **✅** |
| Output | .pyd extension | JIT in memory | CMake project | **Standalone native binary** |

Existing tools were built for **data science and math matrix problems**.  
FastPy is built for **low-latency, bit-twiddling systems programming** — the exact  
architecture of a chess engine.

---

## Current Status

FastPy is in **early architectural development**.

- [x] Project vision and architecture defined
- [x] Core module structure designed
- [x] Speed-first manifesto established
- [ ] Phase 1 MVP implementation
- [ ] Basic bitboard operation transpilation
- [ ] Hardware intrinsic mappings
- [ ] First benchmark results
- [ ] Example chess engine

---

## How To Contribute

FastPy is an open-source project released under the MIT License.  
All skill levels are welcome. Here is where help is needed most:

**Core Development**
- Implementing the `core/parser.py` AST visitor
- Building the `core/emitter.py` C++ code generator
- Writing chess-specific patterns in `core/intrinsics.py`

**Testing**
- Writing test cases for bitboard operations
- Benchmarking generated C++ against pure Python and hand-written C++
- Testing on different hardware (Intel, AMD, Apple Silicon, ARM)

**Documentation**
- Writing guides for chess engine developers new to FastPy
- Documenting the FastPy dialect rules
- Translating documentation

**To contribute:**
1. Fork this repository
2. Create a feature branch
3. Submit a Pull Request with a clear description

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting.  
All contributors are expected to follow our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## A Note on AI-Assisted Development

FastPy was conceived and architecturally designed by **Gokul Chandar** through  
an extensive research and brainstorming process assisted by Google Gemini and  
Claude (Anthropic). The core vision, strategic decisions, and project direction  
are entirely human-driven.

AI tools serve as development assistants in this project — writing code modules  
under human architectural oversight. We believe in being transparent about this.  
The open-source community's human contributors, testers, and reviewers are what  
will make FastPy real.

---

## Creator

**Gokul Chandar** ([@g-c-3](https://github.com/g-c-3))  
*Vision, Architecture, and Project Direction*

AI Collaboration

Mind (Gemini): Ideation and brainstorming
Body (ChatGPT): System design, planning, and implementation
Soul (Claude): Refinement, clarity, and documentation
Human (Gokul Chandar): Final decisions, integration, testing, debugging, and project ownership

---

## License

FastPy is released under the [MIT License](LICENSE).  
You are free to use, modify, and distribute this software — including in  
commercial projects — with no restrictions beyond retaining the copyright notice.

---

*"Write logic with the speed and beauty of Python.*  
*Run it with the terrifying, metal-shredding velocity of optimized C++."*

# FastPy — Architecture

## Pipeline Overview

```
Python source (.py)
      │
      ▼
┌─────────────────┐
│   parser.py     │  ast.parse() → walks AST → builds IRModule dataclass tree
└────────┬────────┘
         │  IRModule
         ▼
┌─────────────────┐
│ type_system.py  │  validates annotations → builds TypeRegistry
└────────┬────────┘
         │  TypeCheckResult + TypeRegistry
         ▼
┌─────────────────┐         ┌──────────────────┐
│   emitter.py    │ ──hook──▶  intrinsics.py    │
└────────┬────────┘         └──────────────────┘
         │  C++ string
         ▼
┌─────────────────┐
│  toolchain.py   │  writes temp .cpp → calls GCC/Clang → native binary
└─────────────────┘
         │
         ▼
    main.py  (CLI — wires it all together)
```

## Module Responsibilities

| Module | Input | Output | Must NOT do |
|---|---|---|---|
| `parser.py` | Python source string | `IRModule` | Type validation, C++ generation |
| `type_system.py` | `IRModule` | `TypeRegistry` + errors | C++ generation |
| `emitter.py` | `IRModule` + `TypeRegistry` | C++ string | Compilation, type checking |
| `intrinsics.py` | IR expression node | `str \| None` | Anything else |
| `toolchain.py` | C++ string + output path | Binary + `CompileResult` | IR processing |

Each module has exactly one job. This boundary is a hard rule.

## IR Node Reference

### Top-Level Structure
```python
IRModule(source_file, type_aliases, constants, functions, classes)
IRTypeAlias(name, cpp_type)                 # uint64 = int
IRConstant(name, type_name, value)          # FILE_A: Final[uint64] = 0x01...
IRFunction(name, params, return_type, body, is_method)
IRClass(name, fields, methods)              # → C++ struct
IRField(name, type_name, default_value)     # self.x: uint64 = 0
IRParam(name, type_name)                    # board: uint64
```

### Expression Nodes
```python
IRName(name)                                # board, FILE_A
IRLiteral(value, kind)                      # kind: "int"|"bool"|"none"|"str"|"empty_list"
IRBinOp(left, op, right)                    # op: "+","-","*","/","//","%","<<",">>","|","&","^"
IRUnaryOp(op, operand)                      # op: "~","-","not","+"
IRCompare(left, op, right)                  # op: "==","!=","<",">","<=",">="
IRBoolOp(op, values)                        # op: "and"|"or"
IRCall(func, args, receiver)                # receiver: preserved for method calls on non-names
IRAttribute(obj, attr)                      # board.white_pawns
IRSubscript(obj, index)                     # moves[i]
IRTuple(elements)                           # (from_sq, to_sq)
IRIfExp(condition, body, orelse)            # a if cond else b
```

### Statement Nodes
```python
IRAssign(target, value, type_name)          # type_name=None if no annotation
IRAugAssign(target, op, value)              # alpha += score
IRReturn(value)
IRIf(condition, body, orelse)               # orelse=[IRIf(...)] for elif
IRWhile(condition, body)
IRFor(target, iterable, body)               # range() → C-style for
IRBreak()
IRExprStatement(expr)                       # call used for side effects
```

## Key Design Details

### IRCall.receiver
When parsing `bin(board).count("1")`:
- `func = "<expr>.count"`
- `args = [IRLiteral("1", "str")]`
- `receiver = IRCall(func="bin", args=[IRName("board")])`

The `receiver` field is essential. Without it, the intrinsics module cannot extract `board` to generate `__builtin_popcountll(board)`.

### Type Resolution — The Ground-Truth Table
`type_system.py` maintains `_CPP_TYPE_TABLE` as the authoritative source.
When `uint64 = int` is parsed, the alias name `"uint64"` is checked first against this table.
Result: `uint64 → uint64_t` (correct), not `int → int32_t` (wrong).

The parser's `_try_type_alias` also checks alias name first now (fixed in Session 1).

### Intrinsic Hook
`emitter._emit_expr()` calls `self._intrinsic(node)` before every expression.
`IntrinsicMapper.try_intrinsic()` returns `str | None`.
`emit_module()` auto-wires the mapper via try/import — callers don't manage this.

### Hardware Intrinsics Implemented

| Python | C++ | Instruction | Condition |
|---|---|---|---|
| `bin(x).count("1")` | `__builtin_popcountll(x)` | POPCNT | `func=="<expr>.count"`, arg is `"1"`, receiver is `bin(x)` |
| `(x & -x).bit_length() - 1` | `__builtin_ctzll(x)` | TZCNT | Full inline match — all conditions must hold simultaneously |

TZCNT does NOT fire partially. The full pattern `(x & -x).bit_length() - 1` must be present.
`(x & -x).bit_length() - 2` → no match → baseline C++.

### Operator Precedence Safety
Bitwise operators `|`, `&`, `^`, `<<`, `>>` wrap their operands in parentheses.
C++ bitwise precedence is lower than comparison operators — this prevents subtle bugs in generated code.

### self. Stripping
Inside struct methods, `self.field` → `field` and `self.method()` → `method()`.
Tracked by `CppEmitter._in_method: bool`.

### elif Chain Emission
`IRIf.orelse = [IRIf(...)]` is detected and emitted as `} else if (cond) {` — not nested `} else { if`.
Handled by `_emit_orelse()`.

### for Loop Translation
```python
for i in range(n):      →    for (int32_t i = 0; i < n; i++) {
for i in range(a, b):   →    for (int32_t i = a; i < b; i++) {
for i in range(a,b,s):  →    for (int32_t i = a; i < b; i += s) {
for x in other:         →    /* TODO: for x in other */ {
```

### uint64 Literal Formatting
Large integer constants get ULL suffix and hex formatting:
- `> 0xFFFFFFFF` → `0x0101010101010101ULL`
- `> 0` → `0x000000FFULL`
- `0` → `0ULL`

## C++ Output Structure
```cpp
// FastPy-generated C++ — do not edit directly
#include <cstdint>
#include <climits>
#include <cstdio>
#include <bit>

// --- Forward declarations ---
struct BoardState;

// --- Constants ---
constexpr uint64_t FILE_A = 0x0101010101010101ULL;

struct BoardState {
    uint64_t white_pawns = 0x000000000000FF00ULL;
    // ...
    uint64_t white_pieces() const { ... }
};

int32_t popcount(uint64_t board) {
    return __builtin_popcountll(board);
}
```

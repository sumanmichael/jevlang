# jevlang reference

The full semantics behind the [README](../README.md): every form `~` takes,
the `jev` block, batching, how state is serialized, what the rewrite emits,
the offline backend, and the complete list of known limitations.

## Syntax

### `x ~ question`

`x ~ q` rewrites to `__jev__.ask(x, q)`, which dispatches on the type of `q`.
The three result types are Jev's: `Noul` is a yes/no answered as a
probability, `Score` a position on a scale, `Choice` a picked label.

| `q` | result | notes |
|---|---|---|
| `"statement"` | `Noul` | float subclass, 0 to 1, truthy only at `>= 0.5` |
| `["level0", "level1", ...]` | `Score` | float subclass, may be fractional; default instructions |
| `{"label": "description", ...}` | `Choice` | str subclass; default instructions |
| `("instructions", ["level0", ...])` | `Score` | custom instructions |
| `("instructions", {"label": "desc", ...})` | `Choice` | custom instructions |

```python
if (p := msg ~ "customer wants a refund") > 0.5:
    log(p)

mood = msg ~ ("How frustrated is the customer?", ["calm", "annoyed", "angry"])
if mood >= 1.5:
    ...
```

`Noul` truthiness is the one place jevlang departs from float semantics: a
`Noul` is truthy at `>= 0.5`, not at "nonzero", so `if msg ~ "urgent":` means
"more likely than not". `Score` and `Choice` carry `.probs` (the full
distribution) and `.confidence`; `Score` also carries `.legend`, the
index-to-level-text mapping. Every result carries `.raw`, the SDK's answer
object, for anything not surfaced.

Default instructions, when you skip the tuple form, are "Which level best
describes the state?" for `Score` and "Which option best describes the
state?" for `Choice`.

`~` is rewritten only where the token before it could end an expression (a
name, a literal, or a closing bracket). Unary `~x`, `a & ~b`, and `f(~x)` are
left alone, so bitwise-not still works. The question is one atom: a string,
a bracketed literal, or a dotted call chain. Parenthesize anything larger,
since `msg ~ q + "!"` is `(msg ~ q) + "!"`.

### `jev x "instructions":` block

```python
jev ticket "Which team should handle `body`?":
    case "billing" ("invoices, refunds"): route_billing()
    case "technical" if prob > 0.7: route_tech()
    case "sales": route_sales()
    else: human_review()
```

This is one `Choice` question plus an `if`/`elif`/`else` chain. Each `case`
label becomes an option; the optional `("description")` after the label
describes it to Jev; the optional `if guard` is ANDed onto that branch. `else`
is optional, and without one the block falls through when no case (and no
guard) matches. The instructions string is optional too.

Inside the block, `prob` (probability of the chosen label), `confidence`, and
`probs` (the full label-to-probability dict) are bound as plain local
variables, so guards and bodies can use them. Nested `jev` blocks get distinct
temporaries but share `prob`/`confidence`/`probs`, the same way a nested `for`
loop reuses a loop variable.

### Batching: `ask_all(value, **questions)`

Several questions about one value in one API call. Each keyword takes
anything the right-hand side of `~` takes, and comes back as an attribute of
the same type `~` would return:

```python
from jevlang import ask_all

a = ask_all(
    ticket,
    urgent="is this urgent",
    mood=["calm", "annoyed", "angry"],
    team={"billing": "invoices, refunds", "technical": "bugs, outages"},
)
if a.urgent and a.mood >= 2:
    escalate(a.team)
```

Every question is validated before anything is sent, so a bad question raises
instead of spending a call. Questions about different values cannot share a
call.

Batching is a trade, not a free win. `if t ~ "a" and t ~ "b"` short-circuits,
so a false first answer never asks the second; `ask_all` asks both up front.
Batch the questions you always want; leave a cheap, likely-false gate as a
plain `~`. There is no automatic batching, since `and`/`or` force the first
answer before the second question exists.

## State

The value left of `~` (or after `jev`) is what Jev calls the state. It can be
a `str`, `dict`, `list`, dataclass instance, pydantic model, number, or plain
object, coerced by trying, in order:

1. strings pass through as-is
2. `__jev_state__()` if the object defines one, recursively coercing its result
3. `dataclasses.asdict()` for a dataclass instance
4. `model_dump(mode="json")` for anything with a `model_dump` method
5. `dict`/`list`/`tuple` pass through as JSON
6. numbers are stringified, which is what lets a `Noul` or `Score` be the
   state of a follow-up question
7. the object's public `__dict__` (attributes not starting with `_`), if
   non-empty
8. `str(x)` for anything else

Non-string state is sent as JSON, so instructions can reference field names
with backticks, e.g. `` "Does `body` request a refund?" ``. Define
`__jev_state__(self)` on your own classes to control exactly what gets sent
and to leave out fields that are noise for a given judgment:

```python
@dataclass
class Ticket:
    id: str
    subject: str
    body: str
    plan: str

    def __jev_state__(self):
        return {"subject": self.subject, "body": self.body}
```

## How it works

`.jev` source is rewritten to Python in two passes over the stdlib
`tokenize` stream, then compiled and executed as a normal module.

The `~` pass rewrites `a ~ b` to `__jev__.ask(a, b)`. The block pass turns a
`jev`/`case` block into one `__jev__.choice(...)` call and an `if`/`elif`
chain. `python -m jevlang --show` prints the result. For the threshold/rank/branch
snippet in the README:

```python
if __jev__.ask(msg , "is urgent") > 0.8:                        # threshold
    page_oncall()

ranked = sorted(queue, key=lambda m: __jev__.ask(m , "likely to churn"), reverse=True)   # rank, one call per item

__jev_r0 = __jev__.choice(msg, {"billing": "invoices, refunds", "technical": "bugs, outages"}, "Which team should handle this?"); prob, confidence, probs = __jev_r0.probs[__jev_r0], __jev_r0.confidence, __jev_r0.probs
if __jev_r0 == "billing": route_billing()
elif __jev_r0 == "technical": route_tech()
else: human_review()
```

Both passes keep the line count unchanged (one input line becomes one output
line), which is what keeps tracebacks pointing at the right `.jev` line. Only
the line is preserved, not the column: the caret in a traceback is computed
against the rewritten text, so it can land off-target.

`__jev__` is the `jevlang.runtime` module, bound in every `.jev` file. Its public
names (`ask`, `ask_all`, `noul`, `score`, `choice`, and the result types) are
also importable from `jev`.

Layout:

```
.claude-plugin/    plugin and marketplace manifests, so the skill installs as a Claude Code plugin
jevlang/__init__.py    installs the import hook, exports the public names
jevlang/transform.py   the two rewrite passes
jevlang/runtime.py     result types, state coercion, ask/ask_all/noul/score/choice
jevlang/backend.py     client factory; FakeClient behind JEVLANG_FAKE_JEV=1
jevlang/loader.py      .jev import hook
jevlang/__main__.py    python -m jevlang [--show] file.jev
docs/              this reference, and the tooling notes
examples/          four runnable examples, one per directory; latency script
editors/           .jev highlighting for VS Code and bat
skills/jevlang/    agent skill teaching the syntax and its sharp edges
tests/             pytest suite, runs offline
```

## Fake backend

Running without `TYPESAFE_API_KEY` stops with a note pointing at
`JEVLANG_FAKE_JEV=1`, which substitutes a canned, deterministic backend that
needs no key and no network:

- `noul`: 1.0 if the instructions text appears (case-insensitively) in the
  state text (JSON-serialized when the state is not a string), else 0.0.
- `score`: the index of the first level whose text appears in the state,
  else 0.
- `choice`: the first label whose label or description shares a whole word
  with the state, else the first label.

That is substring matching, not judgment. It exists so the suite can run
offline (`tests/conftest.py` sets it unconditionally) and so you can check
that a file parses and executes. Its answers are not the model's, and reading
them as such is the fastest way to misjudge what jevlang does: a `Noul` comes
back 0.0 or 1.0 where the real model returns a probability, and a `choice`
turns on shared words the model would ignore.

## Known limitations

- The `jev`/`case` block rewrite is line-based (it does not use the
  tokenizer), so a line inside a docstring or string literal that happens to
  look like `jev x:` or `case "a":` is rewritten too. A docstring that merely
  documents jev syntax can even be rejected with a spurious `SyntaxError`, and
  a multi-line string inside a `case` body can end the block early or be
  reported as a bad clause. Keep multi-line strings out of `case` bodies.
- A `jev` header must fit on one line. A header split across lines is not
  recognized as a header at all, and fails later as ordinary `invalid syntax`.
- A literal string state must be parenthesized: `jev ("some state") "q":`.
  Bare trailing strings are read as the instructions, so `jev "some state":`
  has no state left.
- `~` inside an f-string replacement field (`f"{a ~ b}"`) needs Python 3.12 or
  newer, where the tokenizer exposes the expression. On 3.10 and 3.11 the
  f-string is one opaque token, so the `~` is left alone and Python rejects the
  line with `f-string: invalid syntax`, which does not mention jev.
- A `case` guard containing an unparenthesized top-level `lambda x: ...` is
  split at the lambda's colon. Parenthesize it.
- jevlang checks that a `Score` has 2 to 10 levels and a `Choice` 1 to 255
  options before sending, and raises `ValueError` otherwise.
- Accuracy is unmeasured here. Treat every `~` as a fallible judgment; the
  `confidence` guard and an `else` branch are how you contain it.
- Chained `a ~ b ~ c` rewrites to a three-argument `ask()` and fails at run
  time with `ask() missing 1 required positional argument`. Parenthesize.
- No automatic batching. Each `~` and each `jev` block is its own API call;
  batch explicitly with `ask_all`.
- jevlang adds no caching, retry, or async layer of its own; the SDK has its
  own retry policy.
- The test suite runs entirely against the fake backend. The live path has
  been exercised by hand, not by CI.
- No editor reads `.jev` natively. Linting is a pipe through `--show`, not
  lint-on-save, and highlighting means installing the VS Code or bat grammar
  in `editors/`. Anywhere else, mapping the extension to Python gets you most
  of the coloring, with `jev` and `case` left uncolored.
- Both grammars match line shape, not a parse: a unary `~x` colors as the
  question operator, and `case` in a real `match` statement colors as a jev
  keyword. Both are cosmetic, since Python colors them too.

## Versioning

Versions are [semantic](https://semver.org/) and released by
[commitizen](https://commitizen-tools.github.io/commitizen/) from conventional
commits: `cz bump` reads the commits since the last tag, writes the new number
into `pyproject.toml` and `.claude-plugin/plugin.json`, updates
[CHANGELOG.md](../CHANGELOG.md), and tags `vX.Y.Z`. Pushing that tag is what
publishes to PyPI.

jevlang is 0.x, so a breaking change bumps the minor, not the major. Pin
accordingly: `jevlang~=0.1.0` is the safe constraint.

Public, and covered by that promise:

- the `~` grammar and the `jev`/`case` block syntax
- `Noul` truthiness at `>= 0.5`, and `.probs`, `.confidence`, `.legend`, `.raw`
- the `ask`, `ask_all`, `noul`, `score`, `choice` signatures and the names
  exported from `jevlang`
- the `__jev_state__` protocol and the state coercion order above
- the `TYPESAFE_API_KEY` and `JEVLANG_FAKE_JEV` environment variable names
- `python -m jevlang [--show]`

Internal, and free to change in a patch: `jevlang.transform`,
`jevlang.loader`, `jevlang.backend`, the exact Python that the rewrite emits
(only the line-for-line property is promised), and the fake backend's answers.

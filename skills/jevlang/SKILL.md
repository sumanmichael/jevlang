---
name: jevlang
description: Use when writing, editing, or testing .jev files, or when adding judgment-based decision logic (triage, routing, escalation, moderation, approval) to Python where a rule or regex cannot express the condition.
---

# Writing jevlang

jevlang adds two forms to Python, rewritten to plain Python at import time.
Both call [TypeSafe's Jev](https://docs.typesafe.ai), a classifier that
returns numbers and labels, never text. Every call is paid and needs
`TYPESAFE_API_KEY` in the environment.

## Setup

```
pip install jevlang
```

- Judgment code goes in a `.jev` file. A `.py` file cannot contain `~`
  questions or `jev` blocks; Python rejects them as `invalid syntax`.
- Callers `import jevlang` once (installs the import hook), then import the
  `.jev` module by name like any other module on `sys.path`.
- A `.py` file of the same name always wins over the `.jev`, so name them
  differently.
- Keep the `.jev` file small: the judgments and the branches on them. Put
  I/O, orchestration, and anything deterministic in ordinary `.py` files.

```python
# triage.jev
def team(msg):
    jev msg "Which team should handle this?":
        case "billing" ("invoices, refunds, charges"): return "billing"
        case "technical" ("bugs, outages, errors") if confidence > 0.8: return "technical"
        else: return "human"

# app.py
import jevlang
import triage
print(triage.team("I was charged twice"))
```

## The two forms

`x ~ q` becomes `__jev__.ask(x, q)`. The type of `q` picks the question:

| `q` | returns | notes |
|---|---|---|
| `"a statement"` | `Noul` | float 0 to 1, truthy at `>= 0.5`, no `.confidence` |
| `["low", "mid", "high"]` | `Score` | float, may be fractional, 2 to 10 levels |
| `{"label": "description"}` | `Choice` | str, 1 to 255 options |
| `("instructions", [...])` or `("instructions", {...})` | `Score` / `Choice` | custom instructions |

`Score` and `Choice` carry `.probs` and `.confidence`; `Score` also `.legend`.
All carry `.raw`.

The block form is one `Choice` plus an if/elif chain:

```python
jev ticket "Which team should handle this?":
    case "billing" ("invoices, refunds"): return "billing"
    case "technical" ("bugs, outages") if confidence > 0.8: return "technical"
    else: return "human"
```

`prob`, `confidence`, and `probs` are plain locals inside the block.
The `("description")`, the `if guard`, and the `else` are all optional. A
`case` body may span several lines, indented under the `case` line.

## Writing the question

- Statements, not questions: `"the customer wants a refund"`, not `"does
  the customer want a refund?"`. The model scores how true the statement is.
- One judgment per question. `"urgent and angry"` is two questions; ask
  both with `ask_all`.
- Scale levels go low to high, and describe the level, not the number:
  `["calm, stating facts", "frustrated but civil", "angry, strong language"]`.
- Give every `case` label a description unless the label is self-evident.
  The description is what the model matches against.
- Instructions are short and end in the thing to decide. When the state is a
  dict, name fields in backticks: `"Which team should handle `body`?"`.

## What gets sent

The value left of `~` (or after `jev`) is serialized and sent to the API:
strings as-is, dicts/lists/dataclasses/pydantic models as JSON, other objects
as their public `__dict__`. Define `__jev_state__(self)` on a class to send
only the fields the judgment needs, and never send credentials, tokens, or
fields the judgment does not need:

```python
@dataclass
class Ticket:
    id: str
    subject: str
    body: str
    api_key: str

    def __jev_state__(self):
        return {"subject": self.subject, "body": self.body}
```

## Rules that are easy to get wrong

- The question is ONE atom. `msg ~ q + "!"` parses as `(msg ~ q) + "!"`.
  Parenthesize: `msg ~ (q + "!")`.
- Do not chain. `a ~ b ~ c` compiles to a 3-argument `ask()` and dies at run
  time. Use two statements.
- A `jev` header must fit on one line, and a literal string state must be
  parenthesized: `jev ("some text") "q":`, since a bare trailing string is
  read as the instructions.
- No multi-line strings inside `case` bodies; the block pass is line-based
  and will end the block early. The same applies to a docstring that happens
  to contain a line looking like `case "x":`.
- Parenthesize a `lambda` in a `case` guard, or it splits at the lambda colon.
- `~` inside an f-string needs Python 3.12+. On 3.10 and 3.11 compute it into
  a variable first.
- `Noul` is truthy at `>= 0.5`, not at "nonzero". `if msg ~ "urgent":` means
  "more likely than not", and `not (msg ~ "urgent")` is not "definitely not".

## Cost

Every `~` and every `jev` block is one API call. Questions about the SAME
value collapse into one call:

```python
from jevlang import ask_all

a = ask_all(ticket, urgent="is urgent", mood=["calm", "annoyed", "angry"])
if a.urgent and a.mood >= 2: ...
```

This is a trade. `t ~ "a" and t ~ "b"` short-circuits and may ask only one
question; `ask_all` always asks both. Batch what you always need; leave a
cheap, usually-false gate as a plain `~`. Rules go before questions: check
the amount, the plan, the regex first, and only ask the model about what is
left.

## When not to use it

If a rule decides it, write the rule. `~` is for judgments that `==`, a
regex, or a threshold on a real number cannot express. Do not use it for
exact matching, arithmetic, or anything with a deterministic answer.

Treat every answer as fallible. Guard consequential branches on
`confidence` (or on the `Noul` value itself, e.g. `> 0.8`), and give every
block an `else` that escalates to a human or a safe default. Never let a
`jev` block with side effects fall through silently.

## Testing code that uses jevlang

Unit tests should not hit the API. Two seams:

- `JEVLANG_FAKE_JEV=1` (set it in `conftest.py` before `jev` is imported)
  swaps in an offline substring-matching backend. Good for "does this file
  parse and run". Its answers are not the model's: a `Noul` is only ever
  0.0 or 1.0 and a `Choice` picks by shared words.
- To test the branches, patch the runtime. `.jev` code calls
  `jevlang.runtime.ask` and `jevlang.runtime.choice` by attribute at call time:

```python
import jevlang, jevlang.runtime
from jevlang import Noul, Choice

def test_unsure_technical_goes_to_human(monkeypatch):
    c = Choice("technical"); c.probs = {"technical": 0.6, "billing": 0.4}; c.confidence = 0.3
    monkeypatch.setattr(jevlang.runtime, "choice", lambda state, criteria, instructions=None: c)
    monkeypatch.setattr(jevlang.runtime, "ask", lambda state, q: Noul(0.9))
    import triage
    assert triage.team("whatever") == "human"   # confidence 0.3 fails the guard
```

`ask_all` is imported by name into the `.jev` module, so patch it there:
`monkeypatch.setattr(triage, "ask_all", fake)`.

## Checking your work

- `python -m jevlang --show file.jev` prints the generated Python, no API call.
  Read it once after writing a block to confirm the cases and guards landed.
- Lint the generated Python: `python -m jevlang --show f.jev | ruff check
  --stdin-filename f.jev -`. Line numbers match the `.jev` source. Add
  `builtins = ["__jev__"]` under `[tool.ruff]` so the rewrite is not an
  undefined name.
- Run one real call against the live model before shipping a new question;
  the fake backend cannot tell you whether the wording works.

## Errors and what they mean

| message | cause |
|---|---|
| `SyntaxError: invalid syntax` on a line with `~` | the file is `.py`, not `.jev`, or the import hook is not installed (`import jevlang` first) |
| `TypeError: ask() missing 1 required positional argument: 'q'` | chained `a ~ b ~ c` |
| `SyntaxError: jev: a literal string state must be parenthesized` | `jev "text":`; write `jev ("text") "q":` |
| `f-string: invalid syntax` | `~` inside an f-string on Python < 3.12 |
| `TypeSafeError: No API key was provided` | set `TYPESAFE_API_KEY`, or `JEVLANG_FAKE_JEV=1` for a smoke run |
| `ValueError` before any call | a `Score` outside 2 to 10 levels or a `Choice` outside 1 to 255 options |

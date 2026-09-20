<h1 align="center">jevlang</h1>

<p align="center">The simplest way to write decision workflows in Python.</p>

<p align="center"><i>Python with a smart <code>if</code>.</i></p>

<p align="center">
<a href="https://github.com/sumanmichael/jevlang/actions/workflows/ci.yml"><img src="https://github.com/sumanmichael/jevlang/actions/workflows/ci.yml/badge.svg" alt="ci"></a>
<img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="python 3.10+">
<a href="https://github.com/sumanmichael/jevlang/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT"></a>
</p>

<p align="center"><img src="https://raw.githubusercontent.com/sumanmichael/jevlang/main/assets/demo-triage-and-routing.gif" alt="two .jev modules imported from plain Python: one routes support tickets to a team, one ranks an inbox by urgency" width="820"></p>

```python
if ticket ~ "the customer wants a refund":
    route("billing")
```

`~` asks a question about a value and gets back a number or a label, never
text. Here it is a probability, and the `if` fires at `>= 0.5`. The model
answering is [TypeSafe's Jev](https://docs.typesafe.ai), a hosted classifier
that judges instead of writes.

Four things to know first:

- `.jev` is Python plus two forms: `x ~ question` and a `jev`/`case` block.
  Files are rewritten to plain Python at import time. No new interpreter.
- Every `~` is one call to TypeSafe's API. It needs a key and is paid per call.
- The value left of `~` is what gets sent. Keep secrets out of it.
- Answers are probabilities, not facts. Guard the branches that matter.

It is a prototype: tested, working, with its limits listed below.

## Quick start

Python 3.10 or newer.

```
pip install jevlang
export TYPESAFE_API_KEY=...
```

`hello.jev`:

```python
msg = "I was charged twice, please refund one of them"

if msg ~ "the customer wants a refund":
    print("billing")
else:
    print("not billing")
```

```
python -m jevlang hello.jev          # billing
python -m jevlang --show hello.jev   # print the plain Python it becomes, no API call
```

### From Python

Keep the jev bits in a `.jev` module and import it. `import jevlang` installs an
import hook, after which `.jev` files on `sys.path` import like any other
module.

`triage.jev`:

```python
def wants_refund(msg):
    return msg ~ "the customer wants a refund"

def team(msg):
    jev msg "Which team should handle this?":
        case "billing" ("invoices, refunds, charges"): return "billing"
        case "technical" ("bugs, outages, errors"): return "technical"
        else: return "human"
```

`app.py`, ordinary Python:

```python
import jevlang          # installs the .jev import hook
import triage       # loads triage.jev

msg = "I was charged twice, please refund one of them"
if triage.wants_refund(msg):
    print("route:", triage.team(msg))   # route: billing
```

Callers get back floats and strings (subclasses carrying `.probs` and
friends), so nothing else in your codebase needs to know jevlang exists. A
`.py` file always shadows a `.jev` file of the same name, so the hook can
never hijack an existing module.

### Let your agent write it

Paste this into Claude Code, Codex, Cursor, or whatever writes your code:

```
Install the jevlang skill. If you are in Claude Code, run
`claude plugin marketplace add sumanmichael/jevlang`, then
`claude plugin install jevlang@jevlang`. In any other agent, run
`npx skills add sumanmichael/jevlang` and select your agent. Use one
installation method. You can read the skill directly at
https://github.com/sumanmichael/jevlang/blob/main/skills/jevlang/SKILL.md
(raw: https://raw.githubusercontent.com/sumanmichael/jevlang/main/skills/jevlang/SKILL.md).
Then use the jevlang skill when working on this project.
```

The skill covers the syntax, how to phrase a question, what gets sent to the
API, how to test without a key, and the errors it will hit. It is the one
file [`skills/jevlang/SKILL.md`](https://github.com/sumanmichael/jevlang/blob/main/skills/jevlang/SKILL.md); with no tooling
at all, `curl` that into `.claude/skills/jevlang/SKILL.md`.

## Three questions

The type of the question picks the answer:

| question   | ask it                                            | get back                       |
|------------|---------------------------------------------------|--------------------------------|
| Is it?     | `msg ~ "is urgent"`                               | probability, 0 to 1            |
| How much?  | `msg ~ ["calm", "annoyed", "angry"]`              | position on the scale, 0 to 2  |
| Which one? | `msg ~ {"billing": "refunds", "tech": "outages"}` | one of the labels              |

A string is yes/no, a list is a scale, a dict is options. Answers are numbers
and labels, so you threshold, rank, or branch on them:

```python
if msg ~ "is urgent" > 0.8:                        # threshold
    page_oncall()

ranked = sorted(queue, key=lambda m: m ~ "likely to churn", reverse=True)   # rank, one call per item

jev msg "Which team should handle this?":          # branch
    case "billing" ("invoices, refunds"): route_billing()
    case "technical" ("bugs, outages"): route_tech()
    else: human_review()
```

The `jev` block is one "which one?" question plus an `if`/`elif`/`else`
chain. The `("description")` after each label tells the model what the label
means.

## A whole workflow

```python
from jevlang import ask_all

def triage(ticket):
    if ticket ~ "an automated out-of-office reply":
        return "ignore"

    a = ask_all(ticket, urgent="is urgent", mood=["calm", "annoyed", "angry"])
    if a.urgent and a.mood >= 2:
        return "human"

    jev ticket "Which team should handle this?":
        case "billing" ("invoices, refunds") if confidence > 0.8: return "billing"
        case "technical" ("bugs, outages") if confidence > 0.8: return "technical"
        else: return "human"
```

A gate that is usually false, two questions batched into one call, a branch
that only fires when the model is sure, and a human fallback. There is no
graph: no nodes, no runner, no state object threaded between steps. It is a
function. You call it, test it, and step through it in a debugger.

The runnable version, with a `Ticket` dataclass that controls what gets sent,
is [`examples/support/route.jev`](https://github.com/sumanmichael/jevlang/blob/main/examples/support/route.jev). Three more
examples are indexed in [`examples/README.md`](https://github.com/sumanmichael/jevlang/blob/main/examples/README.md).

## Confidence

Every answer carries its own uncertainty, which is where the "act, confirm,
or hand to a human" policy hangs:

- Yes/no: the answer is the probability. `msg ~ "is urgent"` at 0.93 and at
  0.55 are both truthy, and you can tell them apart with `>`.
- Scale and options: `.probs` is the full distribution and `.confidence`
  summarizes how peaked it is, 0 to 1. Flat means nothing clearly won.
- Inside a `jev` block, `prob`, `confidence`, and `probs` are plain local
  variables, so a `case ... if confidence > 0.8:` guard reads as written.

Accuracy is unmeasured here. Treat every `~` as fallible, and give every
consequential branch a guard and an `else`.

## Why not a prompt, why not a graph

```python
resp = llm("Is this ticket urgent? Answer yes or no.\n\n" + body)
if "yes" in resp.lower():
    ...
```

```python
if body ~ "is urgent":
    ...
```

The first asks a model to write, then parses what it wrote. The second gets a
number back. There is no free text to parse, and nothing generated means
nothing decoded: Jev runs one forward pass and returns a distribution.
Measured from a laptop against the live API, one question and five questions
batched in one call both came back in about half a second (medians 505 ms
and 460 ms; `examples/latency.py` reproduces it, about 12 paid calls).

The other way this gets solved is a workflow framework: the decision becomes
a graph, the branches become edges, and the logic moves into a runner you no
longer step through. jevlang keeps the decision in the language it was
already written in, and adds one operator.

## Syntax at a glance

`x ~ q` dispatches on the type of `q`:

| `q` | result |
|---|---|
| `"statement"` | `Noul`: float, 0 to 1, truthy at `>= 0.5` |
| `["level0", "level1", ...]` | `Score`: float, may be fractional, 2 to 10 levels |
| `{"label": "description", ...}` | `Choice`: str, 1 to 255 options |
| `("instructions", [...])` or `("instructions", {...})` | same, with your own instructions |

`Score` and `Choice` carry `.probs` and `.confidence`; every result carries
`.raw`. The question is one atom: `msg ~ q + "!"` is `(msg ~ q) + "!"`, so
parenthesize anything larger. `~` does not chain.

```python
jev ticket "Which team should handle `body`?":       # the state, then optional instructions
    case "billing" ("invoices, refunds"): route_billing()
    case "technical" if prob > 0.7: route_tech()   # description and guard both optional
    else: human_review()                           # else optional; no match falls through
```

`ask_all(value, **questions)` asks several questions about one value in one
call; each keyword takes what `~` takes. It is a trade: `t ~ "a" and t ~ "b"`
short-circuits, `ask_all` asks both up front.

The value left of `~` can be a `str`, `dict`, `list`, dataclass, pydantic
model, or plain object; non-strings go as JSON, so instructions can name
fields in backticks. Define `__jev_state__(self)` on a class to control
exactly what is sent.

The full rules, including state coercion order and what the rewrite emits,
are in [`docs/reference.md`](https://github.com/sumanmichael/jevlang/blob/main/docs/reference.md).

## How it works

`.jev` source is rewritten to Python in two passes over the stdlib `tokenize`
stream, then compiled and executed as a normal module. `a ~ b` becomes
`__jev__.ask(a, b)`; a `jev`/`case` block becomes one `__jev__.choice(...)`
call and an `if`/`elif` chain. One input line becomes one output line, so
tracebacks point at the right `.jev` line. `python -m jevlang --show file.jev`
prints the result without making a call.

## Limitations

- Every `~` is a paid network call to a hosted service, and the value left of
  it is sent there. There is no caching, retry, or async layer of jevlang's
  own; the SDK has its own retry policy.
- Accuracy is unmeasured. The test suite runs against an offline stub; the
  live path has been exercised by hand, not by CI.
- The `jev`/`case` rewrite is line-based: a `jev` header must fit on one line,
  a literal string state must be parenthesized (`jev ("text") "q":`), and
  multi-line strings inside a `case` body can end the block early.
- `~` inside an f-string needs Python 3.12 or newer. On 3.10 and 3.11 the
  line fails with `f-string: invalid syntax`.
- No automatic batching. Each `~` and each `jev` block is its own call unless
  you use `ask_all`.
- No editor reads `.jev` natively. Linting is a pipe through `--show`, and
  highlighting means installing the grammar in `editors/`.

The complete list, with the parser edge cases, is at the end of
[`docs/reference.md`](https://github.com/sumanmichael/jevlang/blob/main/docs/reference.md#known-limitations).

## Development

```
git clone https://github.com/sumanmichael/jevlang && cd jevlang && uv sync
uv run pytest        # 101 tests, all offline
```

Running without `TYPESAFE_API_KEY` stops with a note pointing at
`JEVLANG_FAKE_JEV=1`, a substring-matching stub that needs no key. It checks
that a file parses and runs. Its answers are not the model's: a `Noul` comes
back 0.0 or 1.0, and a `Choice` turns on shared words.

Linting through `ruff` and the VS Code and `bat` grammars are covered in
[`docs/tooling.md`](https://github.com/sumanmichael/jevlang/blob/main/docs/tooling.md).

Releases are cut with `uv run cz bump`, which writes the new version into
`pyproject.toml` and the plugin manifest, updates the changelog, and tags
`vX.Y.Z`; pushing that tag publishes to PyPI. jevlang is 0.x, so a breaking
change bumps the minor. What counts as one is in
[`docs/reference.md`](https://github.com/sumanmichael/jevlang/blob/main/docs/reference.md#versioning).

## License

MIT. See [LICENSE](https://github.com/sumanmichael/jevlang/blob/main/LICENSE).

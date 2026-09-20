# Examples

Each one is a small, whole decision. Run them against the real model:

```
export TYPESAFE_API_KEY=...
uv run python -m jevlang examples/support/route.jev
uv run python -m jevlang examples/inbox/rank.jev
uv run python -m jevlang examples/expenses/approve.jev
uv run python -m jevlang examples/moderation/screen.jev
```

| Example | Shows |
| --- | --- |
| [`support/route.jev`](support/route.jev) | a `~` gate, one `ask_all` batch, a `jev`/`case` block, `__jev_state__` |
| [`inbox/rank.jev`](inbox/rank.jev) | scoring once and sorting by the result |
| [`expenses/approve.jev`](expenses/approve.jev) | rules before questions, an f-string header, `confidence` guards |
| [`moderation/screen.jev`](moderation/screen.jev) | `ask_all`, a `Noul` threshold, a `Score` with `.confidence` |

Add `--show` to any of those to print the plain Python the file becomes. That
one needs no key.

Without a key the run stops and tells you about `JEVLANG_FAKE_JEV=1`, which
swaps in a substring-matching stub. Use it to check that a file parses and
runs; do not read its answers as the model's. It returns only 0.0 or 1.0 for a
`Noul`, so every example above comes out blunter than the real thing, and
`expenses` and `moderation` turn on wording the model would ignore.

`latency.py` is not a jev file. It is the benchmark behind the README's
latency numbers, and it needs a real key:

```
uv run python examples/latency.py
```

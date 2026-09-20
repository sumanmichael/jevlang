# Tooling

Linting, syntax highlighting, and the agent skill. None of this is needed to
run jevlang; all of it makes editing `.jev` files less annoying.

## Linting

`.jev` is not Python. `a ~ b` is a `SyntaxError`, because `~` is a unary
operator, so no linter or language server reads a `.jev` file directly.
Renaming it to `.jev.py` does not help: the syntax is still rejected on every
question line, and the import hook only matches `.jev`.

Lint the Python it becomes instead. Both rewrite passes map one input line to
one output line, so the reported line numbers point back at the `.jev` source:

```
uv run python -m jevlang --show app.jev | ruff check --stdin-filename app.jev -
```

```
F821 Undefined name `undefined_name`
 --> app.jev:3:12
  |
1 | def f(t):
2 |     x = __jev__.ask(t , "urgent")
3 |     return undefined_name(x)
  |            ^^^^^^^^^^^^^^
```

Two rules need telling about the rewrite, once, in your `pyproject.toml`:

```toml
[tool.ruff]
builtins = ["__jev__"]  # the runtime name both rewrite passes call into

[tool.ruff.lint.per-file-ignores]
"*.jev" = ["F841"]  # a jev block always binds prob/confidence/probs, used or not
```

Without the first, every rewritten question line is an undefined name. The
second is scoped to `*.jev`, so unused variables are still reported in your
`.py` files.

## Syntax highlighting

On GitHub, one line in `.gitattributes` does it:

```
*.jev linguist-language=Python
```

Without it, `.jev` files render as grey plain text in the repo browser and in
every diff. Copy that line into any repo that holds them.

In VS Code, copy or symlink [`editors/vscode`](../editors/vscode) into your
extensions folder:

```
ln -s "$PWD/editors/vscode" ~/.vscode/extensions/jevlang
```

The obvious alternative colors the file too:

```json
"files.associations": {"*.jev": "python"}
```

but it hands the buffer to Pylance as Python, which then reports a syntax
error on every `~` line. The extension declares `.jev` as its own language
whose grammar includes `source.python`, so the coloring survives and the type
checker has nothing to bind to. `jev` and `case` color as keywords, `~` as an
operator, and a `~` inside a string or comment stays a string or comment.

In the terminal, [`editors/bat`](../editors/bat) does the same for `bat`, which
is what the README demo is running:

```
cp editors/bat/jev.sublime-syntax "$(bat --config-dir)/syntaxes/" && bat cache --build
```

Any other editor that maps an extension to a language gets you Python-level
coloring; `jev` and `case` will not be keywords.

## Agent skill

[`skills/jevlang/SKILL.md`](../skills/jevlang/SKILL.md) teaches a coding agent
the syntax, how to write a question, what gets sent to the API, how to test
`.jev` code without a key, and the errors it will hit and what they mean.
The README has a paste-into-your-agent block that installs it. Once installed, the agent picks it
up whenever a task mentions `.jev` or judgment-based routing; nothing has to
be invoked by hand.

The repo doubles as a Claude Code plugin marketplace: `.claude-plugin/`
holds both the plugin manifest and a one-entry marketplace whose source is
the repo root, so `skills/` is discovered without copying. `claude plugin
validate .` checks both files.

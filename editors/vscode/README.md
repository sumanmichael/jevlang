# jevlang syntax highlighting

Copy or symlink this directory into your extensions folder, then reload
the window:

```
ln -s "$PWD/editors/vscode" ~/.vscode/extensions/jevlang
```

It declares `.jev` as its own language, with a grammar that adds `jev`,
`case`, and the `~` operator on top of `source.python`.

The obvious alternative, `"files.associations": {"*.jev": "python"}`, colors
the file too, but it also hands the buffer to Pylance, which reports a syntax
error on every `~` line. A separate language id keeps the coloring and leaves
the Python type checker with nothing to bind to.

Verified against the VS Code TextMate engine: `~` inside a string or comment
stays a string or comment, a docstring that merely names `jev x "q":` is not
treated as a header, and `jev`/`case` color as keywords only at the start of
a line.

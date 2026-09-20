# jev highlighting for bat

`bat` renders `.jev` as plain text until it knows the extension. Install the
syntax and rebuild its cache:

```
mkdir -p "$(bat --config-dir)/syntaxes"
cp jev.sublime-syntax "$(bat --config-dir)/syntaxes/"
bat cache --build
```

`bat file.jev` then colors `jev` and `case` as keywords and `~` as an
operator, on top of Python's own syntax. This is what the README's demo shows.

Verified: `~` inside a string or comment stays a string or comment, and a
docstring that merely names `jev x "q":` is not treated as a header.

# Changelog

Maintained by `cz bump` from [conventional
commits](https://www.conventionalcommits.org/). What counts as a breaking
change is spelled out under
[Versioning](https://github.com/sumanmichael/jevlang/blob/main/docs/reference.md#versioning).

## v0.1.0 (2026-09-21)

First public release.

- The `~` question operator: `x ~ q` dispatches on the type of `q` to a
  `Noul`, `Score`, or `Choice`.
- The `jev`/`case` block: one `Choice` question plus an `if`/`elif`/`else`
  chain, with `prob`, `confidence`, and `probs` bound as locals.
- `ask_all(value, **questions)` for several questions about one value in one
  API call.
- A `.jev` import hook, so `.jev` modules import from plain Python once
  `jevlang` is imported.
- `python -m jevlang [--show] file.jev`.
- `JEVLANG_FAKE_JEV=1`, an offline substring-matching backend that needs no
  key, so the suite and smoke runs work without the network.
- An agent skill (`skills/jevlang/SKILL.md`), installable as a Claude Code
  plugin or through `npx skills`.
- `.jev` syntax highlighting for VS Code and `bat`.

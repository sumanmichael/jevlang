"""Source-to-source rewrite of .jev files into Python.

Two passes, each preserving line count:
  1. rewrite_blocks: `jev x:` / `case` / `else` -> choice() + if/elif/else
  2. rewrite_tilde:  `x ~ q` -> `__jev__.ask(x, q)`
"""

import io
import keyword
import re
import tokenize

OPENERS = {"(": ")", "[": "]", "{": "}"}
CLOSERS = {")": "(", "]": "[", "}": "{"}
_SKIP = (tokenize.COMMENT, tokenize.NL)
_VALUE_KEYWORDS = {"None", "True", "False"}
# PEP 701 (3.12+) splits f-strings into FSTRING_START/MIDDLE/END instead of one
# STRING token. On 3.10/3.11 these are absent and f-strings arrive as STRING.
_FSTRING_START = getattr(tokenize, "FSTRING_START", None)
_FSTRING_END = getattr(tokenize, "FSTRING_END", None)


def _syntax_error(msg, filename, lineno, line=""):
    return SyntaxError(msg, (filename, lineno, 1, line))


def _tokens(source, filename):
    try:
        return list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError) as exc:
        raise _syntax_error(str(exc), filename, 1) from None


def _prev(toks, i):
    j = i - 1
    while j >= 0 and toks[j].type in _SKIP:
        j -= 1
    return j if j >= 0 else None


def _next(toks, i):
    j = i + 1
    while j < len(toks) and toks[j].type in _SKIP:
        j += 1
    return j if j < len(toks) else None


def _is_operand_end(tok):
    """Can this token end an expression? If so, a following `~` is binary."""
    if tok.type in (tokenize.NUMBER, tokenize.STRING, _FSTRING_END):
        return True
    if tok.type == tokenize.NAME:
        return not keyword.iskeyword(tok.string) or tok.string in _VALUE_KEYWORDS
    return tok.type == tokenize.OP and tok.string in CLOSERS


def _match_back(toks, j, filename):
    depth = 0
    while j >= 0:
        t = toks[j]
        if t.type == tokenize.OP:
            if t.string in CLOSERS:
                depth += 1
            elif t.string in OPENERS:
                depth -= 1
                if depth == 0:
                    return j
        j -= 1
    raise _syntax_error("unbalanced brackets before '~'", filename, toks[0].start[0])


def _match_fwd(toks, j, filename):
    depth = 0
    while j < len(toks):
        t = toks[j]
        if t.type == tokenize.OP:
            if t.string in OPENERS:
                depth += 1
            elif t.string in CLOSERS:
                depth -= 1
                if depth == 0:
                    return j
        j += 1
    raise _syntax_error("unbalanced brackets after '~'", filename, toks[0].start[0])


def _fstring_back(toks, j, filename):
    """From an FSTRING_END, return the index of its matching FSTRING_START."""
    depth = 0
    while j >= 0:
        if toks[j].type == _FSTRING_END:
            depth += 1
        elif toks[j].type == _FSTRING_START:
            depth -= 1
            if depth == 0:
                return j
        j -= 1
    raise _syntax_error("unterminated f-string before '~'", filename, toks[0].start[0])


def _fstring_fwd(toks, j, filename):
    """From an FSTRING_START, return the index of its matching FSTRING_END."""
    depth = 0
    while j < len(toks):
        if toks[j].type == _FSTRING_START:
            depth += 1
        elif toks[j].type == _FSTRING_END:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise _syntax_error("unterminated f-string after '~'", filename, toks[0].start[0])


def _end_of_string_run(toks, k, filename):
    """From a STRING or FSTRING_START, walk over implicit concatenation."""
    while True:
        if toks[k].type == _FSTRING_START:
            k = _fstring_fwd(toks, k, filename)
        n = _next(toks, k)
        if n is None or toks[n].type not in (tokenize.STRING, _FSTRING_START):
            return k
        k = n


def _scan_lhs(toks, j, filename):
    """From the token before `~`, walk back over a name/attr/call/index chain.

    Returns the index of the first token of the left operand.
    """
    while True:
        if toks[j].type == _FSTRING_END:
            j = _fstring_back(toks, j, filename)
        elif toks[j].type == tokenize.OP and toks[j].string in CLOSERS:
            j = _match_back(toks, j, filename)
        p = _prev(toks, j)
        if p is None:
            return j
        pt = toks[p]
        if pt.type == tokenize.OP and pt.string == ".":
            k = _prev(toks, p)
            if k is None:
                return j
            j = k
            continue
        if toks[j].type == tokenize.OP and toks[j].string in OPENERS:
            # `name(` or `)(`  or `][`: the bracket is a call/index, keep walking
            if pt.type == tokenize.NAME and not keyword.iskeyword(pt.string):
                j = p
                continue
            if pt.type == tokenize.OP and pt.string in CLOSERS:
                j = p
                continue
            if pt.type in (tokenize.STRING, tokenize.NUMBER, _FSTRING_END):
                # subscripting or calling a literal, e.g. `"abc"[0]`
                j = p
                continue
        if toks[j].type in (tokenize.STRING, _FSTRING_START) and pt.type in (
            tokenize.STRING,
            _FSTRING_END,
        ):
            j = p  # implicit string concatenation
            continue
        return j


def _scan_rhs(toks, i, filename):
    """From the `~` token, walk forward over the question expression.

    Returns the index of the last token of the right operand.
    """
    lineno = toks[i].start[0]
    k = _next(toks, i)
    if k is None or toks[k].type in (tokenize.NEWLINE, tokenize.ENDMARKER):
        raise _syntax_error("expected a question after '~'", filename, lineno)
    t = toks[k]
    if t.type == tokenize.OP and t.string in OPENERS:
        return _match_fwd(toks, k, filename)
    if t.type in (tokenize.STRING, _FSTRING_START):
        return _end_of_string_run(toks, k, filename)
    if t.type == tokenize.NAME and not keyword.iskeyword(t.string):
        while True:
            n = _next(toks, k)
            if n is None:
                return k
            nt = toks[n]
            if nt.type == tokenize.OP and nt.string == ".":
                m = _next(toks, n)
                if m is None or toks[m].type != tokenize.NAME:
                    return k
                k = m
                continue
            if nt.type == tokenize.OP and nt.string in ("(", "["):
                k = _match_fwd(toks, n, filename)
                continue
            return k
    raise _syntax_error("expected a string, list, dict, tuple, or name after '~'", filename, lineno)


def _source_lines(source):
    r"""Split keeping ends, on \n only.

    str.splitlines also breaks on \x0b, \x0c, \x1c, \x1d and \x1e, but tokenize
    counts lines by \n alone. Using splitlines here would shift every edit after
    a form feed onto the wrong physical line.
    """
    return re.split(r"(?<=\n)", source)


def _eol(line):
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


def _apply(source, edits):
    """edits: (row, col, old_len, new_text). Applied last-to-first so offsets hold."""
    lines = _source_lines(source)
    for row, col, old_len, new in sorted(edits, reverse=True):
        line = lines[row - 1]
        lines[row - 1] = line[:col] + new + line[col + old_len:]
    return "".join(lines)


def rewrite_tilde(source, filename="<jev>"):
    toks = _tokens(source, filename)
    edits = []
    for i, tok in enumerate(toks):
        if tok.type != tokenize.OP or tok.string != "~":
            continue
        p = _prev(toks, i)
        if p is None or not _is_operand_end(toks[p]):
            continue  # unary ~
        # chained `a ~ b ~ c` builds a 3-arg ask() that fails at run
        # time rather than here. The grammar does not define chaining.
        lhs = _scan_lhs(toks, p, filename)
        rhs = _scan_rhs(toks, i, filename)
        edits.append((toks[lhs].start[0], toks[lhs].start[1], 0, "__jev__.ask("))
        edits.append((tok.start[0], tok.start[1], 1, ","))
        edits.append((toks[rhs].end[0], toks[rhs].end[1], 0, ")"))
    return _apply(source, edits)

_JEV_RE = re.compile(r"^(?P<ind>[ \t]*)jev\s+(?P<rest>.+?)\s*$")
# block pass is line-based and has no string state, so it misreads
# strings three ways: a `jev`/`case` line inside a literal gets rewritten, a
# docstring documenting jev syntax raises a spurious SyntaxError, and a
# multi-line string inside a case body can end the block early or be diagnosed
# as a bad clause. Token-based block detection if any of that bites.
_CASE_RE = re.compile(
    r"^(?P<ind>[ \t]*)case\s+(?P<label>\"[^\"]*\"|'[^']*')\s*"
    r"(\((?P<desc>\"[^\"]*\"|'[^']*')\))?\s*"
    r"(if\s+(?P<guard>.+?))?\s*$"
)
_ELSE_RE = re.compile(r"^(?P<ind>[ \t]*)else\s*$")


def _skip_string(s, i):
    """From the opening quote at s[i], return the index just past the literal."""
    q = s[i]
    if s[i:i + 3] == q * 3:
        end = s.find(q * 3, i + 3)
        return len(s) if end < 0 else end + 3
    i += 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == q:
            return i + 1
        i += 1
    return len(s)


def _split_clause(raw):
    """Split a clause line at its colon: 'case "a" if d[1:2]: x' -> head, ' x'.

    The colon that ends the clause is the first one outside strings and
    brackets, so colons in guards (slices, dicts, string literals) are safe.
    Returns None when the line has no such colon.
    """
    depth = 0
    i = 0
    while i < len(raw):
        c = raw[i]
        if c in "\"'":
            i = _skip_string(raw, i)
            continue
        if c == "#":
            return None  # rest of the line is a comment
        if c in OPENERS:
            depth += 1
        elif c in CLOSERS:
            depth -= 1
        elif c == ":" and depth == 0:
            # an unparenthesized top-level `lambda x: ...` guard would
            # split here. Parenthesize it; a real expression parse if that bites.
            return raw[:i], raw[i + 1:]
        i += 1
    return None


def _indent(line):
    return len(line) - len(line.lstrip())


def _split_header(rest, lineno, filename):
    """'msg "which dept"' -> ('msg', '"which dept"'); 'msg' -> ('msg', None).

    The instructions are the trailing run of STRING tokens, if any.
    """
    toks = _tokens(rest + "\n", filename)
    toks = [
        t
        for t in toks
        if t.type not in (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER, tokenize.COMMENT)
    ]
    j = len(toks)
    while j > 0:
        if toks[j - 1].type == tokenize.STRING:
            j -= 1
        elif toks[j - 1].type == _FSTRING_END:
            j = _fstring_back(toks, j - 1, filename)  # 3.12+ splits f-strings up
        else:
            break
    if j == 0:
        # Every token is a string, so the trailing-run rule ate the state too.
        msg = "jev: a literal string state must be parenthesized, as jev (\"...\") ..."
        raise _syntax_error(msg, filename, lineno, rest)
    if j == len(toks):
        return rest, None
    cut = toks[j].start[1]
    return rest[:cut].rstrip(), rest[cut:].strip()


def rewrite_blocks(source, filename="<jev>"):
    lines = _source_lines(source)
    out = list(lines)
    counter = 0
    for i, line in enumerate(lines):
        raw = line.rstrip("\r\n")
        if "jev" not in raw:
            continue
        split = _split_clause(raw)
        if split is None:
            continue
        head, tail = split
        m = _JEV_RE.match(head)
        if not m or (tail.strip() and not tail.lstrip().startswith("#")):
            continue
        head_ind = len(m.group("ind"))
        state, instr = _split_header(m.group("rest"), i + 1, filename)
        case_ind = None
        crit, cases = [], []
        saw_else = False
        for j in range(i + 1, len(lines)):
            row = lines[j].rstrip("\r\n")
            if row.strip() == "" or row.lstrip().startswith("#"):
                continue
            ind = _indent(row)
            if ind <= head_ind:
                break
            if case_ind is None:
                case_ind = ind
            if ind != case_ind:
                continue  # body of a case (or a nested jev); leave for later passes
            clause = _split_clause(row)
            cm = em = None
            if clause:
                cm = _CASE_RE.match(clause[0])
                em = None if cm else _ELSE_RE.match(clause[0])
            if saw_else and (cm or em):
                raise _syntax_error("jev: 'else' must be the last clause", filename, j + 1, lines[j])
            if cm:
                crit.append((cm.group("label"), cm.group("desc") or "None"))
                cases.append((j, cm.group("label"), cm.group("guard"), clause[1]))
            elif em:
                saw_else = True
                cases.append((j, None, None, clause[1]))
            else:
                raise _syntax_error("jev: expected 'case' or 'else'", filename, j + 1, lines[j])
        if not crit:
            raise _syntax_error("jev: block has no case", filename, i + 1, line)
        r = f"__jev_r{counter}"
        counter += 1
        pad = m.group("ind")
        crit_src = "{" + ", ".join(f"{k}: {v}" for k, v in crit) + "}"
        instr_src = f", {instr}" if instr else ""
        out[i] = (
            f"{pad}{r} = __jev__.choice({state}, {crit_src}{instr_src}); "
            f"prob, confidence, probs = {r}.probs[{r}], {r}.confidence, {r}.probs"
            f"{_eol(line)}"
        )
        first = True
        for idx, label, guard, body in cases:
            nl = _eol(lines[idx])
            if label is None:
                out[idx] = f"{pad}else:{body}{nl}"
            else:
                cond = f"{r} == {label}"
                if guard:
                    cond += f" and ({guard})"
                out[idx] = f"{pad}{'if' if first else 'elif'} {cond}:{body}{nl}"
            first = False
    return "".join(out)


def transform(source, filename="<jev>"):
    return rewrite_tilde(rewrite_blocks(source, filename), filename)

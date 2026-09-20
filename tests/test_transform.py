import sys

import pytest

from jevlang.transform import rewrite_tilde


@pytest.mark.parametrize(
    "src,expected",
    [
        ('x = msg ~ "urgent"\n', 'x = __jev__.ask(msg , "urgent")\n'),
        ('if msg ~ "urgent" > 0.8:\n    pass\n', 'if __jev__.ask(msg , "urgent") > 0.8:\n    pass\n'),
        ('v = t.body ~ ["calm", "angry"]\n', 'v = __jev__.ask(t.body , ["calm", "angry"])\n'),
        ('v = f(a) ~ {"b": "c"}\n', 'v = __jev__.ask(f(a) , {"b": "c"})\n'),
        ('v = (a + b) ~ "q"\n', 'v = __jev__.ask((a + b) , "q")\n'),
        ('v = d["k"] ~ crit\n', 'v = __jev__.ask(d["k"] , crit)\n'),
        ('v = obj.meth(1)[2] ~ "q"\n', 'v = __jev__.ask(obj.meth(1)[2] , "q")\n'),
        ('v = msg ~ "a" "b"\n', 'v = __jev__.ask(msg , "a" "b")\n'),
        ('v = x ~ ("How?", ["a", "b"])\n', 'v = __jev__.ask(x , ("How?", ["a", "b"]))\n'),
        ('v = x ~ crit.table\n', 'v = __jev__.ask(x , crit.table)\n'),
        ('v = x ~ crit.get("k")\n', 'v = __jev__.ask(x , crit.get("k"))\n'),
        (
            'r = sorted(t, key=lambda i: i ~ "churn")\n',
            'r = sorted(t, key=lambda i: __jev__.ask(i , "churn"))\n',
        ),
        (
            'v = a ~ "p" and b ~ "q"\n',
            'v = __jev__.ask(a , "p") and __jev__.ask(b , "q")\n',
        ),
        ('v = a ~ {\n    "x": "y",\n}\n', 'v = __jev__.ask(a , {\n    "x": "y",\n})\n'),
        ('v = ["hi", "bye"] ~ "greeting"\n', 'v = __jev__.ask(["hi", "bye"] , "greeting")\n'),
    ],
)
def test_binary_tilde_rewrites(src, expected):
    assert rewrite_tilde(src) == expected


@pytest.mark.parametrize(
    "src",
    [
        "y = ~x\n",
        "y = a & ~b\n",
        's = "a ~ b"\n',
        "y = not ~x\n",
        "z = f(~x)\n",
    ],
)
def test_unary_tilde_untouched(src):
    assert rewrite_tilde(src) == src


def test_tilde_preserves_line_count():
    src = 'a = 1\nb = a ~ {\n  "k": "v",\n}\nc = 2\n'
    assert len(rewrite_tilde(src).splitlines()) == len(src.splitlines())


def test_tilde_missing_rhs_is_syntax_error():
    with pytest.raises(SyntaxError):
        rewrite_tilde("x = a ~\n")


@pytest.mark.parametrize(
    "src,expected",
    [
        ('v = f"hi {n}" ~ "urgent"\n', 'v = __jev__.ask(f"hi {n}" , "urgent")\n'),
        ('v = msg ~ f"is this {topic}?"\n', 'v = __jev__.ask(msg , f"is this {topic}?")\n'),
        ('v = f"a {b}".upper() ~ "q"\n', 'v = __jev__.ask(f"a {b}".upper() , "q")\n'),
        ('v = f"{a}"[0] ~ "q"\n', 'v = __jev__.ask(f"{a}"[0] , "q")\n'),
        ('v = msg ~ f"one {t}" f"two"\n', 'v = __jev__.ask(msg , f"one {t}" f"two")\n'),
    ],
)
def test_fstring_operands(src, expected):
    # Python 3.12 (PEP 701) tokenizes f-strings as FSTRING_START/MIDDLE/END
    # rather than one STRING token, so both scans must handle them.
    assert rewrite_tilde(src) == expected


@pytest.mark.parametrize(
    "src,expected",
    [
        ('v = "abc"[0] ~ "q"\n', 'v = __jev__.ask("abc"[0] , "q")\n'),
        ('v = "a" "b" ~ "q"\n', 'v = __jev__.ask("a" "b" , "q")\n'),
    ],
)
def test_literal_lhs(src, expected):
    assert rewrite_tilde(src) == expected


@pytest.mark.skipif(sys.version_info < (3, 12), reason="needs PEP 701 tokenization")
def test_tilde_inside_fstring_expression():
    src = 'v = f"{a ~ b}"\n'
    assert rewrite_tilde(src) == 'v = f"{__jev__.ask(a , b)}"\n'


import ast

from jevlang.transform import rewrite_blocks, transform

BLOCK = '''def route(msg):
    jev msg "which department":
        case "billing" ("invoices, refunds"): return "b"
        case "technical" if prob > 0.7:
            log(probs)
            return "t"
        # comment
        case "sales": return "s"
        else:
            return "h"
    return None
'''

BLOCK_OUT = '''def route(msg):
    __jev_r0 = __jev__.choice(msg, {"billing": "invoices, refunds", "technical": None, "sales": None}, "which department"); prob, confidence, probs = __jev_r0.probs[__jev_r0], __jev_r0.confidence, __jev_r0.probs
    if __jev_r0 == "billing": return "b"
    elif __jev_r0 == "technical" and (prob > 0.7):
            log(probs)
            return "t"
        # comment
    elif __jev_r0 == "sales": return "s"
    else:
            return "h"
    return None
'''


def test_block_rewrite_exact():
    assert rewrite_blocks(BLOCK) == BLOCK_OUT


def test_block_output_parses_and_keeps_line_count():
    out = rewrite_blocks(BLOCK)
    ast.parse(out)
    assert len(out.splitlines()) == len(BLOCK.splitlines())


def test_block_without_instructions_or_else():
    src = 'jev x:\n    case "a": y = 1\n    case "b": y = 2\n'
    out = rewrite_blocks(src)
    assert out.startswith('__jev_r0 = __jev__.choice(x, {"a": None, "b": None}); ')
    assert 'if __jev_r0 == "a": y = 1\n' in out
    assert 'elif __jev_r0 == "b": y = 2\n' in out
    ast.parse(out)


def test_block_state_can_be_expression():
    src = 'jev t.body "q":\n    case "a": pass\n'
    assert rewrite_blocks(src).startswith('__jev_r0 = __jev__.choice(t.body, {"a": None}, "q"); ')


def test_nested_blocks_get_distinct_temps():
    src = '''jev t "outer":
    case "a":
        jev t "inner":
            case "x": r = 1
            else: r = 2
    case "b" if confidence > 0.9:
        r = 3
    else:
        r = 4
'''
    out = rewrite_blocks(src)
    ast.parse(out)
    assert "__jev_r0" in out and "__jev_r1" in out
    assert len(out.splitlines()) == len(src.splitlines())


def test_block_bad_line_is_syntax_error_with_lineno():
    with pytest.raises(SyntaxError) as e:
        rewrite_blocks("jev t:\n    foo()\n", filename="f.jev")
    assert e.value.filename == "f.jev"
    assert e.value.lineno == 2


def test_block_with_no_cases_is_syntax_error():
    with pytest.raises(SyntaxError) as e:
        rewrite_blocks("jev t:\nprint(1)\n", filename="f.jev")
    assert e.value.lineno == 1


def test_block_missing_state_is_syntax_error():
    with pytest.raises(SyntaxError):
        rewrite_blocks('jev "only instructions":\n    case "a": pass\n')


def test_transform_runs_both_passes():
    src = 'jev msg "q":\n    case "a" if msg ~ "x" > 0.5: pass\n'
    out = transform(src)
    ast.parse(out)
    assert '__jev__.ask(msg , "x")' in out
    assert "__jev__.choice(msg," in out


def test_transform_plain_python_unchanged():
    src = "def f(x):\n    return ~x & 3\n"
    assert transform(src) == src


@pytest.mark.parametrize(
    "guard",
    [
        'x == "note: value"',  # colon inside a string literal
        "d[1:2]",  # slice
        'x == {"k": "v"}',  # dict literal
        'd[1:2] == {"k": "v:w"}',  # all three at once
    ],
)
def test_case_guard_may_contain_colons(guard):
    # The clause-ending colon is the first one outside strings and brackets;
    # splitting at the first colon after `if` truncates the guard instead.
    src = f'jev t "q":\n    case "a" if {guard}: pass\n    else: pass\n'
    out = rewrite_blocks(src)
    ast.parse(out)
    assert f'if __jev_r0 == "a" and ({guard}):' in out


def test_else_only_block_is_syntax_error():
    with pytest.raises(SyntaxError):
        rewrite_blocks('jev t "q":\n    else: pass\n')


@pytest.mark.parametrize(
    "src",
    [
        'jev t "q":\n    else: pass\n    case "a": pass\n',  # else before a case
        'jev t "q":\n    case "a": pass\n    else: pass\n    else: pass\n',  # two elses
    ],
)
def test_else_must_be_the_last_clause(src):
    with pytest.raises(SyntaxError):
        rewrite_blocks(src)


def test_nested_block_keeps_tab_indentation():
    src = 'class C:\n\tdef f(self):\n\t\tjev t "q":\n\t\t\tcase "a":\n\t\t\t\treturn 1\n\t\t\telse:\n\t\t\t\treturn 2\n'
    out = rewrite_blocks(src)
    ast.parse(out)  # space-padded lines beside tab-indented siblings raise TabError
    assert "\t\t__jev_r0 = " in out
    assert '\t\tif __jev_r0 == "a":' in out


def test_block_line_with_no_colon_is_not_a_header():
    src = 'jev_count = 1\nx = {"k": "v"}\n'
    assert rewrite_blocks(src) == src


def test_form_feed_does_not_shift_edits():
    # str.splitlines also breaks on \x0c, but tokenize counts lines by \n alone,
    # so a page break used to push every later edit onto the wrong line.
    src = 'def a():\n    return 1\n\x0c\ndef b(m):\n    return m ~ "urgent"\n'
    out = transform(src)
    ast.parse(out)
    assert out.split("\n")[4] == '    return __jev__.ask(m , "urgent")'
    assert len(out.split("\n")) == len(src.split("\n"))


@pytest.mark.parametrize(
    "header,expected",
    [
        ('jev t f"Which {k}?":', 'f"Which {k}?"'),
        ('jev t "a" f"b":', '"a" f"b"'),
    ],
)
def test_fstring_header_instructions(header, expected):
    # On 3.12+ an f-string ends with FSTRING_END rather than STRING, so the
    # trailing-instruction walk has to step over it or the state swallows it.
    out = rewrite_blocks(f'{header}\n    case "x": pass\n')
    ast.parse(out)
    assert f'__jev__.choice(t, {{"x": None}}, {expected})' in out


@pytest.mark.parametrize("head", ['jev "some state":', 'jev "some state" "which dept":'])
def test_literal_string_state_error_names_the_workaround(head):
    with pytest.raises(SyntaxError, match="parenthesized"):
        rewrite_blocks(head + '\n    case "a": pass\n')


def test_block_preserves_crlf_and_missing_final_newline():
    out = rewrite_blocks('jev m "q":\r\n    case "a": pass\r\n')
    assert all(line.endswith("\r") for line in out.split("\n")[:-1])
    assert not rewrite_blocks('jev m "q":\n    case "a": pass').endswith("\n")

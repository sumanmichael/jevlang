import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import jevlang  # installs the import hook
from jevlang.loader import load_file

ROOT = Path(__file__).resolve().parents[1]


def test_import_hook_loads_jev_module(tmp_path, monkeypatch):
    (tmp_path / "mymod.jev").write_text('def hot(m):\n    return m ~ "urgent"\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = __import__("mymod")
    assert mod.hot("this is urgent") == 1.0
    assert mod.hot("calm") == 0.0


def test_traceback_points_at_jev_line(tmp_path):
    src = textwrap.dedent(
        '''
        x = 1
        if "abc" ~ "abc":
            raise RuntimeError("boom")
        '''
    ).lstrip()
    f = tmp_path / "boom.jev"
    f.write_text(src)
    with pytest.raises(RuntimeError) as e:
        load_file(str(f), "boom_mod")
    tb = e.traceback[-1]
    assert tb.path.name == "boom.jev"
    assert tb.lineno + 1 == 3  # pytest traceback lineno is 0-based


def test_syntax_error_reports_jev_filename(tmp_path):
    f = tmp_path / "bad.jev"
    f.write_text("jev x:\n    nope()\n")
    with pytest.raises(SyntaxError) as e:
        load_file(str(f), "bad_mod")
    assert e.value.filename.endswith("bad.jev")
    assert e.value.lineno == 2


def test_example_runs_end_to_end():
    r = subprocess.run(
        [sys.executable, "-m", "jevlang", str(ROOT / "examples" / "support" / "route.jev")],
        capture_output=True,
        text=True,
        env={"JEVLANG_FAKE_JEV": "1", "PYTHONPATH": str(ROOT)},
    )
    assert r.returncode == 0, r.stderr
    assert "T-1 -> technical" in r.stdout
    assert "T-2 -> billing" in r.stdout
    assert "T-3 -> human" in r.stdout


@pytest.mark.parametrize("path", sorted((ROOT / "examples").glob("*/*.jev")), ids=lambda p: p.parent.name)
def test_every_example_runs(path):
    # the examples are documentation; a rewrite that breaks one should fail here
    r = subprocess.run(
        [sys.executable, "-m", "jevlang", str(path)],
        capture_output=True,
        text=True,
        env={"JEVLANG_FAKE_JEV": "1", "PYTHONPATH": str(ROOT)},
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_show_prints_rewritten_python():
    r = subprocess.run(
        [sys.executable, "-m", "jevlang", "--show", str(ROOT / "examples" / "support" / "route.jev")],
        capture_output=True,
        text=True,
        env={"JEVLANG_FAKE_JEV": "1", "PYTHONPATH": str(ROOT)},
    )
    assert r.returncode == 0, r.stderr
    assert "__jev__.choice(" in r.stdout
    assert "__jev__.ask(" in r.stdout


def test_load_file_does_not_cache_a_module_that_failed(tmp_path):
    # A half-executed module left in sys.modules makes a later import return
    # the broken object instead of re-running the file.
    src = tmp_path / "boom.jev"
    src.write_text('x = "a" ~ "q"\nraise ValueError("boom")\n')
    with pytest.raises(ValueError):
        load_file(str(src), module_name="boom_mod")
    assert "boom_mod" not in sys.modules

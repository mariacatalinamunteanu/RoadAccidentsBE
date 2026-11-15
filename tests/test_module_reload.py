"""GAP 11 (see TEST_GAPS.md): every test starts a new Python process, so no test could see that a RUNNING app keeps an
old pipeline.py in memory. That happened for real: AttributeError "module 'pipeline' has no attribute 'explain'"
after app.py and pipeline.py were changed while the server ran. This test changes a module file inside one process."""
import importlib
import os
import sys

from module_reload import fresh


def _write(path, text, bump_ns):
    path.write_text(text, encoding="utf-8")
    st_ = os.stat(path)
    os.utime(path, ns=(st_.st_atime_ns, st_.st_mtime_ns + bump_ns))  # make sure the time stamp moves


def test_changed_module_is_reloaded(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    f = tmp_path / "demo_pipeline.py"
    _write(f, "VALUE = 1\n", 0)
    mod = importlib.import_module("demo_pipeline")
    mod = fresh(mod)
    assert mod.VALUE == 1 and not hasattr(mod, "explain")

    _write(f, "VALUE = 2\n\ndef explain(k):\n    return k\n", 2_000_000_000)  # file edited while 'server' runs
    mod = fresh(mod)
    assert mod.VALUE == 2 and mod.explain("x") == "x"
    sys.modules.pop("demo_pipeline", None)


def test_unchanged_module_is_not_reloaded(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    f = tmp_path / "demo_same.py"
    _write(f, "VALUE = 1\n", 0)
    mod = fresh(importlib.import_module("demo_same"))
    mod.MARK = "still here"  # a reload would wipe this attribute
    assert fresh(mod).MARK == "still here"
    sys.modules.pop("demo_same", None)

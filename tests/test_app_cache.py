"""GAP 9 (see TEST_GAPS.md): the other tests always start from an empty cache, so they cannot see that a running
app keeps serving an OLD file after pipeline.py rewrote it. That happened for real (KeyError "['dataset', 'tabs'] not
in index" after the pipeline was rerun). This test rewrites a file between two reads in the same process."""
import os

import pandas as pd

import app_data as D


def test_cached_csv_is_read_again_after_the_file_changes(tmp_path):
    f = tmp_path / "steps.csv"
    pd.DataFrame({"order": ["1"], "step": ["old"]}).to_csv(f, index=False, encoding="utf-8-sig")
    first = D.read_csv(f)
    assert list(first.columns) == ["order", "step"]

    pd.DataFrame({"order": ["1"], "step": ["new"], "dataset": ["x"], "tabs": ["y"]}).to_csv(
        f, index=False, encoding="utf-8-sig")
    st_ = os.stat(f)
    os.utime(f, ns=(st_.st_atime_ns, st_.st_mtime_ns + 1_000_000_000))  # make sure the time stamp moves

    second = D.read_csv(f)
    assert {"dataset", "tabs"} <= set(second.columns)
    assert second.step.iloc[0] == "new"


def test_unchanged_file_comes_from_the_cache(tmp_path, monkeypatch):
    f = tmp_path / "a.csv"
    pd.DataFrame({"x": [1]}).to_csv(f, index=False)
    calls = []
    real = D.pd.read_csv
    monkeypatch.setattr(D.pd, "read_csv", lambda *a, **k: calls.append(1) or real(*a, **k))
    D.read_csv(f)
    D.read_csv(f)
    assert len(calls) == 1  # the second call is served from the cache (st.cache_data returns a copy, not the same object)

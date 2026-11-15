"""The 'Prompt history' sub-tab (Pipeline & method) shows the student's file as it is and never changes it
(decisions D47, D49)."""
import re

import app_data as D
import pipeline as P

APP = (P.ROOT / "app.py").read_text(encoding="utf-8")


def test_prompt_history_is_a_subtab_right_of_decision_log_and_tests():
    # decision D49: sub-tab of Pipeline & method, directly right of "Decision log & tests"; no main tab any more
    assert '"Decision log & tests", "📝 Prompt history"]' in APP
    main_tabs = APP[APP.index("tab0, tab1"):].splitlines()[0]
    assert "Prompt history" not in main_tabs
    body = APP[APP.index("def pipeline_tab"):APP.index("# =================================================================== DATA EXPLORER")]
    assert "with t6:" in body and "prompt_history_tab()" in body


def test_tab_shows_the_file_content_unchanged():
    if not P.PROMPT_HISTORY.exists():
        return
    assert D.load_prompt_history() == P.PROMPT_HISTORY.read_text(encoding="utf-8")


def test_no_code_writes_the_prompt_history():
    # the student's rule: Claude (and the app) never change Prompt history.txt
    for f in ["app.py", "app_data.py", "pipeline.py"]:
        src = (P.ROOT / f).read_text(encoding="utf-8")
        assert not re.search(r"PROMPT_HISTORY\)?\.(write_text|write_bytes|open\()", src), f
        assert not re.search(r"open\([^)]*PROMPT_HISTORY[^)]*['\"][wa]", src), f

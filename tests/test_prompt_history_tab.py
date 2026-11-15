"""The 'Prompt history' tab shows the student's file as it is and never changes it (decision D47)."""
import re

import app_data as D
import pipeline as P

APP = (P.ROOT / "app.py").read_text(encoding="utf-8")


def test_tab_exists_and_is_filled_by_its_function():
    assert '"📝 Prompt history"' in APP and "prompt_history_tab()" in APP


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

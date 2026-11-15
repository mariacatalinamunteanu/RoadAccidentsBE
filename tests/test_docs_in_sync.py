"""GAP 13 (see TEST_GAPS.md): the documentation must follow the code (decision D50).

The consistency check found TEST_GAPS.md claiming 39 tests (real: 42), a test file missing from CLAUDE.md and
decisions without their "Later changed" link. These tests fail as soon as the documents fall behind again."""
import ast
import re

import pandas as pd

import pipeline as P

ROOT = P.ROOT
TEST_FILES = sorted((ROOT / "tests").glob("test_*.py"))


def n_tests(path):
    return sum(1 for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
               if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"))


def test_test_gaps_states_the_real_number_of_tests():
    text = (ROOT / "tests" / "TEST_GAPS.md").read_text(encoding="utf-8")
    claimed = int(re.search(r"all, (\d+) tests", text).group(1))
    assert claimed == sum(n_tests(f) for f in TEST_FILES)


def test_claude_md_lists_every_test_file_with_its_count():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    for f in TEST_FILES:
        m = re.search(rf"`{re.escape(f.name)}` \((\d+)", text)
        assert m, f"{f.name} missing in CLAUDE.md"
        assert int(m.group(1)) == n_tests(f), f"{f.name}: CLAUDE.md says {m.group(1)}, file has {n_tests(f)}"


def test_claude_md_lists_every_pipeline_step():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    section = text[text.index("## Pipeline steps"):text.index("## Data agreements")]
    for code in P.STEP_DISPLAY_ORDER:
        assert re.search(rf"\b{code}\b", section), code


def test_step_data_shown_in_the_app_matches_pipeline_py():
    if not P.OUT_STEPS.exists():
        return
    s = pd.read_csv(P.OUT_STEPS, encoding="utf-8-sig").set_index("order")
    assert list(s.index) == P.STEP_DISPLAY_ORDER, "rerun `python pipeline.py`"
    for code in s.index:
        assert (s.loc[code, "dataset"], s.loc[code, "tabs"]) == P.STEP_CONTEXT[code], f"{code}: rerun pipeline.py"


def test_decisions_are_numbered_without_gaps_or_duplicates():
    ids = [int(x) for x in re.findall(r"^### D(\d+)", (ROOT / "decision_log.md").read_text(encoding="utf-8"), re.M)]
    assert ids == list(range(1, len(ids) + 1))


def test_lineage_table_names_only_existing_steps():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    lineage = app[app.index("LINEAGE = ["):app.index("def pipeline_tab")]
    codes = set(re.findall(r"\b([APGC]\d)\b", lineage))
    assert codes and codes <= set(P.STEP_DISPLAY_ORDER), codes - set(P.STEP_DISPLAY_ORDER)
    assert not re.search(r"[Ss]teps? [1-8]\b", lineage)  # old step numbers (renamed in D46)


def test_every_decision_says_who_decided_and_claude_choices_are_marked():
    # decision D51: every entry has 'Decided by'; a choice by Claude carries ☐ (open) or ✅ (confirmed by the student)
    text = (ROOT / "decision_log.md").read_text(encoding="utf-8")
    for d, body in re.findall(r"^### (D\d+)(.*?)(?=^### D\d+|\Z)", text, flags=re.S | re.M):
        who = re.search(r"- \*\*Decided by:\*\* (.*)", body)  # rest of that line
        assert who, f"{d}: no 'Decided by' line"
        claude_choice = who.group(1).startswith("Claude") or "+ Claude" in who.group(1)
        if claude_choice:
            marks = body.splitlines()[0] + who.group(1)  # title line + 'Decided by' line
            assert "☐" in marks or "✅" in marks, f"{d}: choice by Claude without ☐ / ✅"

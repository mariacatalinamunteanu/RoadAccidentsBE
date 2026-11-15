"""Reload a project module when its .py file changed on disk.

A running Streamlit server keeps imported modules (pipeline.py, app_data.py) in memory. When app.py is changed it is
rerun, but an older pipeline.py could stay loaded -> AttributeError "module 'pipeline' has no attribute 'explain'"
(decision_log D37). app.py calls fresh() at every run, so a refresh always uses the files as they are on disk.
"""
import importlib
from pathlib import Path


def fresh(module):
    """Return `module`, reloaded first if its source file was modified since it was (re)loaded."""
    mtime = Path(module.__file__).stat().st_mtime_ns
    if getattr(module, "_loaded_mtime", None) != mtime:
        module = importlib.reload(module)
        module._loaded_mtime = mtime
    return module

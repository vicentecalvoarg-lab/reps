# Auto-generated wrapper for app/pagina/analysis_ips.py
import importlib.util
import sys
from pathlib import Path
import streamlit as st
import pandas as pd
# Try to load original moved to .orig
orig_path = Path(__file__).with_name("analysis_ips.orig.py")
spec = importlib.util.spec_from_file_location("analysis_ips_orig", str(orig_path))
orig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orig)
def _collect_outputs_from_module(mod):
    outputs = {}
    try:
        for k, v in getattr(mod, "__dict__", {}).items():
            if isinstance(v, pd.DataFrame):
                outputs[k] = v
    except Exception:
        pass
    try:
        for k, v in st.session_state.items():
            if isinstance(v, pd.DataFrame):
                outputs[k] = v
    except Exception:
        pass
    return outputs

def run(*args, **kwargs):
    ctx = {"outputs": {}}
    try:
        res = orig.run(*args, **kwargs)
    except Exception:
        res = None
    if isinstance(res, dict) and "outputs" in res:
        ctx = res
    else:
        ctx["outputs"].update(_collect_outputs_from_module(orig))
    try:
        st.session_state.setdefault("master_pages_outputs", {}).update(ctx.get("outputs", {}))
    except Exception:
        pass
    return ctx

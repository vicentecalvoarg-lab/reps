# main.py
"""
Main entry for the multi-page Streamlit dashboard (lazy imports).

Default parquet path defaults to c:/reps/data/output_data.parquet (can be overridden via env vars).
This version normalizes the 'nit IPS' column and constructs nits_display with normalized NITs
so pages receive NITs in a consistent format.
"""
# --- ensure project root is on sys.path BEFORE other imports -----------------
from pathlib import Path
import sys
_root = Path(__file__).resolve().parent  # this file sits at project root or adjust if in /app
_root_str = str(_root)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)
# ------------------------------------------------------------------------------

import os
import traceback
import importlib
import streamlit as st
import pandas as pd
import numpy as np
import re

st.set_page_config(layout="wide", page_title="Dashboard — Multi módulo (lazy imports)")

# ---------------- Configuration / Data loading ----------------

def get_parquet_path():
    # prefer explicit OUTPUT_PARQUET env var (allows separation from GIRO_PARQUET)
    p = os.environ.get("OUTPUT_PARQUET") or os.environ.get("GIRO_PARQUET")
    if p:
        return p
    # ruta por defecto:
    return r"C:/REPS/data/output_data.parquet"

@st.cache_resource(show_spinner=False)
def load_parquet(path: str) -> pd.DataFrame:
    try:
        p = Path(path)
        if not p.exists():
            st.warning(f"Parquet not found at: {path}")
            return pd.DataFrame()
        # Use pandas to read parquet; engines will be tried in helper modules if needed
        df = pd.read_parquet(path)
        return df
    except Exception as e:
        st.error(f"Error cargando parquet: {e}")
        return pd.DataFrame()

# ---------------- UI: sidebar global filters & data path overrides ----------------

st.sidebar.title("Dashboard — Menú principal")

# Show and allow override of core data paths (these will be set in env for downstream modules)
st.sidebar.markdown("#### Rutas de datos (puedes sobreescribir)")
env_output = os.environ.get("OUTPUT_PARQUET", "")
env_giro = os.environ.get("GIRO_PARQUET", "")
env_sugeridos = os.environ.get("SUGERIDOS_PATH", "")

default_output = env_output or r"C:/REPS/data/output_data.parquet"
default_giro = env_giro or r"C:/REPS/data/giro.parquet"
default_sugeridos = env_sugeridos or r"C:/REPS/data/sugeridos.xlsx"

# allow user to override paths in UI; changes are applied immediately to os.environ
user_output = st.sidebar.text_input("Ruta output_data.parquet (OUTPUT_PARQUET)", value=default_output, key="ui_output_parquet")
user_giro = st.sidebar.text_input("Ruta Giro (GIRO_PARQUET)", value=default_giro, key="ui_giro_parquet")
user_sugeridos = st.sidebar.text_input("Ruta Sugeridos (SUGERIDOS_PATH)", value=default_sugeridos, key="ui_sugeridos_path")

# Apply environment overrides so downstream modules reading os.environ pick them up
os.environ["OUTPUT_PARQUET"] = user_output
os.environ["GIRO_PARQUET"] = user_giro
os.environ["SUGERIDOS_PATH"] = user_sugeridos

st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Selecciona módulo:",
    options=[
        "Análisis IPS",
        "Giro Directo",
        "Comparaciones de IPS",
        "MASTER IPS"
    ]
)

st.sidebar.markdown("---")
factor_operativo = st.sidebar.slider("Factor operativo", 0.50, 1.50, 1.00, 0.01, key='global_factor')

# ---------------- Data ----------------

parquet_path = get_parquet_path()
st.sidebar.caption(f"Datos (OUTPUT_PARQUET): {parquet_path}")

with st.spinner("Cargando datos (parquet)..."):
    df_all = load_parquet(parquet_path)

if df_all is None:
    df_all = pd.DataFrame()
df_filtered = df_all.copy()

# ---------------- Normalize NITs in df_all ----------------
def _clean_nit_str(s):
    if pd.isna(s):
        return None
    s = str(s)
    cleaned = re.sub(r'\D', '', s)
    cleaned = cleaned.lstrip('0')
    return cleaned if cleaned != '' else None

# detect candidate NIT column
nit_col_candidates = [c for c in df_all.columns if 'nit' in c.lower()] if not df_all.empty else []
if 'nit IPS' in df_all.columns:
    nit_src_col = 'nit IPS'
elif nit_col_candidates:
    nit_src_col = nit_col_candidates[0]
else:
    nit_src_col = None

if nit_src_col is not None and not df_all.empty:
    try:
        df_all = df_all.copy()
        df_all['nit_normalized'] = df_all[nit_src_col].apply(_clean_nit_str)
        nits_from_col = sorted(df_all['nit_normalized'].dropna().unique().tolist())
    except Exception:
        nits_from_col = []
else:
    nits_from_col = []

# ---------------- Build nits_display robustly (cap for performance) ----------------
nits_display = []
try:
    from app.data import explode_nits_regex  # optional helper in project
    exploded = explode_nits_regex(df_all, nit_src_col if nit_src_col else '')
    if exploded is not None and not exploded.empty and 'nit_token' in exploded.columns:
        nits_display = sorted({re.sub(r'\D', '', str(x)) for x in exploded['nit_token'].dropna().astype(str).tolist()})
except Exception:
    pass

if not nits_display and nits_from_col:
    nits_display = sorted({n for n in nits_from_col if n is not None})

nits_display = [n for n in nits_display if n]  # remove empty
nits_display = sorted(set(nits_display))[:20000]

# ---------------- Helper: dynamic import and run ----------------

def import_and_run(module_path: str, run_args: tuple):
    """
    Import module by string (e.g. 'app.pagina.analysis_ips') and call run(*run_args).
    Shows traceback in UI if import or run fails.
    """
    try:
        mod = importlib.import_module(module_path)
    except Exception:
        st.error(f"Error importando módulo {module_path}. Ver traceback abajo.")
        st.exception(traceback.format_exc())
        return
    if not hasattr(mod, "run"):
        st.error(f"El módulo {module_path} no expone la función 'run(...)'")
        return
    try:
        mod.run(*run_args)
    except Exception:
        st.error(f"Error ejecutando {module_path}.run(...) — ver traceback abajo.")
        st.exception(traceback.format_exc())

# ---------------- Page dispatch (lazy imports) ----------------

st.title("Dashboard — Menú principal")
st.write("---")
st.write("Filas luego de cargar datos:", f"{len(df_filtered):,}")

filters = {"factor_operativo": factor_operativo}

if page == "Análisis IPS":
    import_and_run("app.pagina.analysis_ips", (filters, df_filtered, df_all))
elif page == "Giro Directo":
    import_and_run("app.pagina.giro_directo", (filters, df_filtered, df_all))
elif page == "Comparaciones de IPS":
    import_and_run("app.pagina.comparaciones", (df_filtered, nits_display, df_all, filters))
elif page == "MASTER IPS":
    import_and_run("app.pagina.master_ips", (filters, df_filtered, df_all))
else:
    st.info("Página no implementada aún.")

st.write("---")
st.caption("Dashboard — Multi módulo • Integración por main.py (lazy imports)")

"""
Main entry for the multi-page Streamlit dashboard (lazy imports).

Default parquet path defaults to c:/reps/data/output_data.parquet (can be overridden via GIRO_PARQUET).
This version normalizes the 'nit IPS' column (remueve comas/no-dígitos) y construye nits_display
con NITs normalizados para que las páginas reciban NITs en formato consistente.
"""
# --- ensure project root is on sys.path BEFORE other imports -----------------
from pathlib import Path
import sys
_root = Path(__file__).resolve().parent.parent  # parent of the "app" folder
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
    p = os.environ.get("GIRO_PARQUET")
    if p:
        return p
    # ruta por defecto corregida:
    return r"C:/REPS/data/output_data.parquet"

@st.cache_resource(show_spinner=False)
def load_parquet(path: str) -> pd.DataFrame:
    try:
        p = Path(path)
        if not p.exists():
            st.warning(f"Parquet not found at: {path}")
            return pd.DataFrame()
        df = pd.read_parquet(path)
        return df
    except Exception as e:
        st.error(f"Error cargando parquet: {e}")
        return pd.DataFrame()

# ---------------- UI: sidebar global filters & navigation ----------------

st.sidebar.title("Dashboard — Menú principal")
page = st.sidebar.radio("Selecciona módulo:",
                        options=[
                            "Análisis IPS",
                            "Giro Directo",
                            "Comparaciones de IPS",
                            "MASTER IPS"
                        ])

st.sidebar.markdown("---")
factor_operativo = st.sidebar.slider("Factor operativo", 0.50, 1.50, 1.00, 0.01, key='global_factor')

# ---------------- Data ----------------

parquet_path = get_parquet_path()
st.sidebar.caption(f"Datos: {parquet_path}")

with st.spinner("Cargando datos (parquet)..."):
    df_all = load_parquet(parquet_path)

if df_all is None:
    df_all = pd.DataFrame()
df_filtered = df_all.copy()

# ---------------- Normalize NITs in df_all ----------------
# If the dataset has a column that looks like 'nit' (case-insensitive), prepare a normalized version
def _clean_nit_str(s):
    if pd.isna(s):
        return None
    s = str(s)
    # Remove any non-digit characters (commas, dots, spaces, etc.)
    cleaned = re.sub(r'\D', '', s)
    # Strip leading zeros if any (optional)
    cleaned = cleaned.lstrip('0')
    return cleaned if cleaned != '' else None

# Prefer the specific column we saw: 'nit IPS'
nit_col_candidates = [c for c in df_all.columns if 'nit' in c.lower()]
if 'nit IPS' in df_all.columns:
    nit_src_col = 'nit IPS'
elif nit_col_candidates:
    nit_src_col = nit_col_candidates[0]
else:
    nit_src_col = None

if nit_src_col is not None:
    # create/overwrite a normalized column always named 'nit_normalized' for downstream use
    try:
        df_all = df_all.copy()
        df_all['nit_normalized'] = df_all[nit_src_col].apply(_clean_nit_str)
        # dropna then unique
        nits_from_col = sorted(df_all['nit_normalized'].dropna().unique().tolist())
    except Exception:
        nits_from_col = []
else:
    nits_from_col = []

# ---------------- Build nits_display robustly (cap for performance) ----------------
nits_display = []
# If there's an explode utility, try it; otherwise use the normalized column values
try:
    from app.data import explode_nits_regex
    exploded = explode_nits_regex(df_all, nit_src_col if nit_src_col else '')
    if exploded is not None and not exploded.empty and 'nit_token' in exploded.columns:
        # Explode may give tokens already cleaned; ensure we also strip non-digits
        nits_display = sorted({re.sub(r'\D', '', str(x)) for x in exploded['nit_token'].dropna().astype(str).tolist()})
except Exception:
    pass

# Fallback to values from the normalized column
if not nits_display and nits_from_col:
    nits_display = sorted({n for n in nits_from_col if n is not None})

# Final cleanup & cap
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
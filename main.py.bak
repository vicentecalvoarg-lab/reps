"""
Main entry for the multi-page Streamlit dashboard (lazy imports).

This version ensures the project root (parent of the 'app' folder) is added to sys.path
so imports like 'app.pagina.*' work reliably when Streamlit launches.
Default parquet path is set to c:/reps/data/output.data.parquet (can be overridden via GIRO_PARQUET).
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

st.set_page_config(layout="wide", page_title="Dashboard — Multi módulo (lazy imports)")

# ---------------- Configuration / Data loading ----------------

def get_parquet_path():
    # Prefer environment variable, otherwise default to the path you provided
    p = os.environ.get("GIRO_PARQUET")
    if p:
        return p
    return r"c:/reps/data/output.data.parquet"

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
                            "Comparaciones de IPS"
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

# ---------------- Build nits_display robustly ----------------
nits_display = []
if not df_all.empty:
    # try explode_nits_regex if available
    try:
        from app.data import explode_nits_regex
        exploded = explode_nits_regex(df_all, 'nit IPS')
        if exploded is not None and not exploded.empty and 'nit_token' in exploded.columns:
            nits_display = sorted(exploded['nit_token'].dropna().unique().tolist())
    except Exception:
        exploded = None

    # fallback: look for columns that contain 'nit'
    if not nits_display:
        for cand in ['nit','NIT','Nit','nit IPS','NIT IPS','NIT_Prestador','nit_prestador','nit_ips']:
            for col in df_all.columns:
                if col.lower() == cand.lower():
                    try:
                        nits_display = sorted(df_all[col].dropna().astype(str).unique().tolist())
                        break
                    except Exception:
                        continue
            if nits_display:
                break

# cap size for performance (optional)
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
else:
    st.info("Página no implementada aún.")

st.write("---")
st.caption("Dashboard — Multi módulo • Integración por main.py (lazy imports)")
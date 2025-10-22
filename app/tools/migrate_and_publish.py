#!/usr/bin/env python3
"""
Migration & publish helper (UPDATED: REPLACE_CORE activated and core file contents embedded).

This script will:
 - Create a full backup of the project root (tar.gz).
 - Move legacy page modules to .orig (analysis/analisis, comparaciones, giro_directo) and write wrappers.
 - Replace core files (main.py, master_ips_impl.py, master_ips_05.py, master_ips_export.py, master_ips.py)
   with the improved versions embedded below (safely creating .bak copies).
 - Initialize git (if needed), stage and commit changes.
 - Optionally create a GitHub repo and push (requires GITHUB_TOKEN).

USAGE (dry-run first):
  python tools/migrate_and_publish.py --project-root "C:/REPS" --dry-run

APPLY CHANGES:
  python tools/migrate_and_publish.py --project-root "C:/REPS"

PUSH TO GITHUB:
  Set GITHUB_TOKEN in environment and run:
  python tools/migrate_and_publish.py --project-root "C:/REPS" --push --owner <owner> --repo <repo>

Notes:
 - This version has REPLACE_CORE = True and includes final contents for the core files.
 - The script creates backups (.bak) for overwritten files and renames originals to .orig.py for wrapped files.
"""

import argparse
from pathlib import Path
import shutil
import tarfile
import subprocess
import sys
import os
from datetime import datetime

try:
    from github import Github
except Exception:
    Github = None

# Files we will wrap (original will be moved to .orig)
# Include both Spanish and English possible filenames for the analysis module.
WRAP_FILES = [
    "app/pagina/analisis_ips.py",
    "app/pagina/analysis_ips.py",
    "app/pagina/comparaciones.py",
    "app/pagina/giro_directo.py",
]

# Where optional local wrappers can live (tools/wrappers/<filename>)
LOCAL_WRAPPERS_DIR = Path(__file__).parent / "wrappers"

# --- CORE FILE CONTENTS TO WRITE (REPLACE_CORE=True) ----------------
# These variables contain the final content for the files to be replaced.
# If you want to edit them before running the script, open this file and change the strings.

MAIN_PY = r'''# main.py
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
'''

MASTER_IMPL_PY = r'''# app/pagina/master_ips_impl.py
"""
Orquestador maestro para MASTER IPS (con sidebar de filtros).

Descubre y ejecuta en orden los módulos:
 - master_ips_01.py
 - master_ips_02.py
 - master_ips_03.py
 - master_ips_04.py
 - master_ips_05.py

Proporciona helpers en ctx['helpers'] para que los bloques los utilicen.
Expose run(filters, df_filtered, df_all) como entrypoint público.
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import importlib
import sys
import io
import re
import unicodedata
import difflib
import datetime

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ---------------- Helpers (expuestos en ctx['helpers']) ----------------

def _clean_nit_str(s: Optional[str]) -> Optional[str]:
    if pd.isna(s) or s is None:
        return None
    s = str(s)
    cleaned = re.sub(r"\D", "", s)
    cleaned = cleaned.lstrip("0")
    return cleaned if cleaned != "" else None

def _normalize_name_for_match(s: Optional[str]) -> str:
    if pd.isna(s) or s is None:
        return ""
    s = str(s).strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'[\|\-\–\—_/\\]+', ' ', s)
    s = re.sub(r'[^A-Z0-9\s]', '', s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _find_column_like(df: pd.DataFrame, patterns: List[str]) -> Optional[str]:
    if df is None or df.columns is None:
        return None
    cols = df.columns.tolist()
    for pat in patterns:
        for c in cols:
            try:
                if pat.lower() == str(c).lower():
                    return c
            except Exception:
                continue
    for pat in patterns:
        for c in cols:
            try:
                if pat.lower() in str(c).lower():
                    return c
            except Exception:
                continue
    return None

def _ensure_nit_normalized(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "nit_normalized" in df.columns:
        return df
    nit_col = _find_column_like(df, ["nit ips", "nit", "nit_prestador", "NIT"])
    if nit_col is None:
        df["nit_normalized"] = pd.NA
        return df
    try:
        df["nit_normalized"] = df[nit_col].astype(str).apply(_clean_nit_str)
    except Exception:
        df["nit_normalized"] = df[nit_col].astype(str).str.replace(r"\D", "", regex=True).str.lstrip("0")
    return df

def _safe_col_str(df_local: pd.DataFrame, col_name: str) -> pd.Series:
    if col_name is None or col_name not in df_local.columns:
        return pd.Series([""] * len(df_local), index=df_local.index)
    col_obj = df_local.loc[:, col_name]
    if isinstance(col_obj, pd.DataFrame):
        if col_obj.shape[1] == 1:
            s = col_obj.iloc[:, 0].astype(str)
        else:
            def _row_join(x):
                vals = ["" if pd.isna(v) else str(v) for v in x.tolist()]
                vals = [v.strip() for v in vals if v not in ("", "nan", "None")]
                return " | ".join(vals)
            s = col_obj.apply(_row_join, axis=1)
    else:
        try:
            s = col_obj.astype(str)
        except Exception:
            s = col_obj.apply(lambda x: "" if pd.isna(x) else str(x))
    s = s.replace({"nan": "", "None": ""})
    return s.fillna("").astype(str)

@st.cache_data(show_spinner=False)
def load_giro_parquet(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        try:
            return pd.read_parquet(path, engine="pyarrow")
        except Exception:
            try:
                return pd.read_parquet(path, engine="fastparquet")
            except Exception:
                return pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_censo_csv(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    attempts = [
        {"sep": ";", "encoding": "utf-8"},
        {"sep": ";", "encoding": "latin1"},
        {"sep": ",", "encoding": "utf-8"},
        {"sep": ",", "encoding": "latin1"},
        {"sep": None, "engine": "python", "encoding": "utf-8"},
    ]
    for a in attempts:
        try:
            df = pd.read_csv(path, **a)
            df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
            if df.shape[1] > 0:
                return df
        except Exception:
            continue
    try:
        df = pd.read_table(path, engine="python")
        df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_sugeridos_csv(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    attempts = [
        {"sep": ";", "encoding": "utf-8"},
        {"sep": ";", "encoding": "latin1"},
        {"sep": ",", "encoding": "utf-8"},
        {"sep": ",", "encoding": "latin1"},
        {"sep": None, "engine": "python", "encoding": "utf-8"},
    ]
    for a in attempts:
        try:
            df = pd.read_csv(path, **a)
            df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
            if df.shape[1] > 0:
                return df
        except Exception:
            continue
    try:
        df = pd.read_table(path, engine="python")
        df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()

def _build_sede_keys_series(df_local: pd.DataFrame, codigo_cols: List[str], sede_name_col: Optional[str], dept_col: Optional[str], mun_col: Optional[str]) -> pd.Series:
    df_l = df_local.copy()
    df_l['_sede_key_tmp'] = ""
    def safe(col):
        return _safe_col_str(df_l, col).str.strip() if col else pd.Series([""]*len(df_l), index=df_l.index)
    for c in codigo_cols:
        if c in df_l.columns:
            s = safe(c)
            mask = df_l['_sede_key_tmp'] == ""
            df_l.loc[mask & (s != ""), '_sede_key_tmp'] = s[mask & (s != "")]
    if sede_name_col and sede_name_col in df_l.columns:
        s_sede = safe(sede_name_col)
        mask = df_l['_sede_key_tmp'] == ""
        df_l.loc[mask & (s_sede != ""), '_sede_key_tmp'] = s_sede[mask & (s_sede != "")]
    mask = df_l['_sede_key_tmp'] == ""
    nit_s = safe("nit_normalized")
    dept_s = safe(dept_col) if dept_col else pd.Series([""] * len(df_l), index=df_l.index)
    mun_s = safe(mun_col) if mun_col else pd.Series([""] * len(df_l), index=df_l.index)
    fallback = nit_s.fillna("").astype(str) + "|" + dept_s.fillna("").astype(str) + "|" + mun_s.fillna("").astype(str)
    df_l.loc[mask, '_sede_key_tmp'] = fallback[mask]
    return df_l['_sede_key_tmp'].astype(str)

# Helpers dictionary to share with blocks
_helpers = {
    "clean_nit": _clean_nit_str,
    "normalize": _normalize_name_for_match,
    "find_col": _find_column_like,
    "ensure_nit": _ensure_nit_normalized,
    "safe_str": _safe_col_str,
    "load_giro_parquet": load_giro_parquet,
    "load_censo_csv": load_censo_csv,
    "load_sugeridos_csv": load_sugeridos_csv,
    "build_sede_key": _build_sede_keys_series,
}

# ---------------- Block discovery & orchestrator ----------------

def _discover_blocks(folder: Path) -> List[str]:
    """
    Discover only numbered block modules named master_ips_XX.py where XX are digits.
    Excludes files like master_ips_impl.py.
    """
    files = sorted(folder.glob("master_ips_*.py"))
    mod_names = []
    for f in files:
        # only accept names like master_ips_01.py, master_ips_02.py, ... (two digits)
        if re.match(r"^master_ips_\d{2}\.py$", f.name) and "impl" not in f.name:
            mod = f.stem  # e.g. master_ips_01
            mod_names.append(f"app.pagina.{mod}")
    return mod_names

def _execute_blocks(ctx: Dict[str, Any], folder: Path) -> Dict[str, Any]:
    blocks = _discover_blocks(folder)
    ctx.setdefault("outputs", {})
    for module_name in blocks:
        block_label = module_name.split(".")[-1]
        st.sidebar.info(f"Ejecutando bloque: {block_label}")
        st.session_state['last_block'] = block_label
        st.markdown(f"### Ejecutando bloque: {block_label} — {pd.Timestamp.now()}")
        try:
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
                module = sys.modules[module_name]
            else:
                module = importlib.import_module(module_name)
            if hasattr(module, "run") and callable(module.run):
                ctx = module.run(ctx) or ctx
            else:
                st.warning(f"{block_label} no expone run(ctx); lo omito.")
        except Exception as e:
            st.error(f"Error en bloque {block_label}: {e}")
            continue
    return ctx

# ---------------- Public entrypoint ----------------

def run(filters: Dict[str, Any], df_filtered: Optional[pd.DataFrame], df_all: pd.DataFrame):
    """
    Entrypoint that prepares the context, shows sidebar and executes blocks in order.
    """
    folder = Path(__file__).parent
    ctx: Dict[str, Any] = {}
    ctx['filters'] = filters or {}
    ctx['df_all'] = df_all.copy() if df_all is not None else pd.DataFrame()
    ctx['df_filtered'] = df_filtered.copy() if (df_filtered is not None) else None
    # default: use df_filtered if provided else df_all
    ctx['df_result'] = ctx['df_filtered'] if ctx['df_filtered'] is not None else ctx['df_all']
    ctx['helpers'] = _helpers
    # common paths
    ctx['giro_path'] = os.environ.get("GIRO_PARQUET", r"C:/REPS/data/giro.parquet")
    ctx['censo_path'] = os.environ.get("CENSO_PATH", r"C:/REPS/data/censo.csv")
    ctx['sugeridos_path'] = os.environ.get("SUGERIDOS_PATH", r"C:/REPS/data/sugeridos.xlsx")
    ctx['display_options'] = {"escala": 100000}
    ctx['start_ts'] = pd.Timestamp.now()

    # --- Sidebar: build filters using df_all columns ---
    st.sidebar.header("Filtros principales")
    df_ref = ctx['df_all'] if ctx['df_all'] is not None else pd.DataFrame()
    # detect columns
    find_col = _helpers["find_col"]
    level_col = find_col(df_ref, ["nivel", "num nivel", "num nivel atencion", "nivel_atencion"])
    dept_col = find_col(df_ref, ["departamento", "nombre departamento"])
    mun_col = find_col(df_ref, ["municipio", "nombre municipio"])
    service_group_col = find_col(df_ref, ["nom grupo capacidad", "servicio", "nom grupo", "grupo"])
    service_desc_col = find_col(df_ref, ["nom descripcion capacidad", "descripcion", "especialidad"])

    # Level
    nivel_options = ["TODAS"]
    if level_col and level_col in df_ref.columns:
        niveles = sorted(df_ref[level_col].dropna().astype(str).unique().tolist())
        nivel_options += niveles
    selected_nivel = st.sidebar.selectbox("Nivel", options=nivel_options, index=0)

    # Departamento
    dept_options = ["TODAS"]
    if dept_col and dept_col in df_ref.columns:
        dept_options += sorted(df_ref[dept_col].dropna().astype(str).unique().tolist())
    selected_dept = st.sidebar.selectbox("Departamento", options=dept_options, index=0)

    # Municipio (dependent)
    mun_options = ["TODAS"]
    if mun_col and mun_col in df_ref.columns:
        if selected_dept and selected_dept != "TODAS" and dept_col in df_ref.columns:
            mun_vals = sorted(df_ref[df_ref[dept_col].astype(str) == str(selected_dept)][mun_col].dropna().astype(str).unique().tolist())
            mun_options += mun_vals
        else:
            mun_options += sorted(df_ref[mun_col].dropna().astype(str).unique().tolist())
    selected_mun = st.sidebar.selectbox("Municipio", options=mun_options, index=0)

    # Servicio / Especialidad
    svc_options = ["TODAS"]
    if service_group_col and service_group_col in df_ref.columns:
        svc_options += sorted(df_ref[service_group_col].dropna().astype(str).unique().tolist())
    selected_service = st.sidebar.selectbox("Servicio", options=svc_options, index=0)

    spec_options = ["TODAS"]
    if service_desc_col and service_desc_col in df_ref.columns:
        spec_options += sorted(df_ref[service_desc_col].dropna().astype(str).unique().tolist())
    selected_specialty = st.sidebar.selectbox("Especialidad", options=spec_options, index=0)

    st.sidebar.markdown("---")
    max_rows = st.sidebar.number_input("Máx filas a mostrar", min_value=10, max_value=100000, value=500, step=10)
    show_preview = st.sidebar.checkbox("Mostrar preview (primeras N filas)", value=True)

    escala_choice = st.sidebar.selectbox("Escala indicador", options=[("Por 1.000",1000),("Por 10.000",10000),("Por 100.000",100000)], format_func=lambda x: x[0], index=2)
    ctx['display_options']['escala'] = int(escala_choice[1])

    # Giro period selector (if giro.parquet available)
    giro_path = ctx.get('giro_path')
    date_range = None
    if giro_path:
        gtmp = load_giro_parquet(giro_path)
        if gtmp is not None and not gtmp.empty:
            date_col_tmp = find_col(gtmp, ["fecha", "fecha giro", "fecha_giro", "fecha_pago", "date", "periodo"])
            if date_col_tmp and date_col_tmp in gtmp.columns:
                try:
                    gtmp['_parsed_date_tmp'] = pd.to_datetime(gtmp[date_col_tmp], errors='coerce')
                    min_date = gtmp['_parsed_date_tmp'].min()
                    max_date = gtmp['_parsed_date_tmp'].max()
                    default_start = max_date - pd.DateOffset(months=12) if (max_date - min_date).days > 30 else min_date
                    start_date, end_date = st.sidebar.date_input("Periodo giros (desde - hasta)", value=(default_start.date(), max_date.date()))
                    try:
                        date_range = (pd.to_datetime(start_date), pd.to_datetime(end_date))
                    except Exception:
                        date_range = None
                except Exception:
                    date_range = None
    ctx['giro_date_range'] = date_range

    # Save filter selections to ctx['filters']
    ctx['filters'] = {
        "Nivel": selected_nivel,
        "Departamento": selected_dept,
        "Municipio": selected_mun,
        "Servicio": selected_service,
        "Especialidad": selected_specialty,
        "MaxRows": int(max_rows),
        "ShowPreview": bool(show_preview),
    }

    # --- Apply filters to build df_result used by blocks ---
    df_result = ctx['df_all'].copy() if ctx['df_all'] is not None else pd.DataFrame()
    # apply filters
    try:
        if level_col and level_col in df_result.columns and selected_nivel and selected_nivel != "TODAS":
            df_result = df_result[df_result[level_col].astype(str) == str(selected_nivel)]
        if dept_col and dept_col in df_result.columns and selected_dept and selected_dept != "TODAS":
            df_result = df_result[df_result[dept_col].astype(str) == str(selected_dept)]
        if mun_col and mun_col in df_result.columns and selected_mun and selected_mun != "TODAS":
            df_result = df_result[df_result[mun_col].astype(str) == str(selected_mun)]
        if service_group_col and service_group_col in df_result.columns and selected_service and selected_service != "TODAS":
            df_result = df_result[df_result[service_group_col].astype(str) == str(selected_service)]
        if service_desc_col and service_desc_col in df_result.columns and selected_specialty and selected_specialty != "TODAS":
            df_result = df_result[df_result[service_desc_col].astype(str) == str(selected_specialty)]
    except Exception as e:
        st.warning(f"Error aplicando filtros: {e}")

    # ensure nit normalized
    df_result = _helpers["ensure_nit"](df_result)

    ctx['df_result'] = df_result

    # ---------------------
    # Asegurar existencia de _sede_key en df_result (crear una única vez para todos los bloques)
    # Pegar esto justo después de haber construido ctx['df_result'] y antes de ejecutar los bloques
    try:
        df_res = ctx.get('df_result', pd.DataFrame())
        if df_res is None:
            df_res = pd.DataFrame()
        # si falta la columna, la construimos con el helper central
        if '_sede_key' not in df_res.columns:
            # asegurar nit_normalized
            try:
                df_res = ctx['helpers']['ensure_nit'](df_res)
            except Exception:
                # fallback ligero: intentar generar nit_normalized limpiando alguna columna posible
                nitcol = ctx['helpers']['find_col'](df_res, ["nit", "nit ips", "nit_prestador"])
                if nitcol and nitcol in df_res.columns:
                    df_res['nit_normalized'] = df_res[nitcol].astype(str).map(lambda x: re.sub(r"\D","", str(x)).lstrip("0"))
                else:
                    df_res['nit_normalized'] = pd.NA

            # detectar columnas para construir la clave de sede
            codigo_cols = [c for c in df_res.columns if "sede" in str(c).lower() and "cod" in str(c).lower()]
            sede_name_col = ctx['helpers']['find_col'](df_res, ["nom sede", "nombre sede", "nom_sede"])
            dept_col = ctx['helpers']['find_col'](df_res, ["departamento", "nombre departamento"])
            mun_col = ctx['helpers']['find_col'](df_res, ["municipio", "nombre municipio"])

            # construir _sede_key de forma vectorizada
            try:
                df_res['_sede_key'] = ctx['helpers']['build_sede_key'](df_res, codigo_cols, sede_name_col, dept_col, mun_col)
            except Exception as e:
                # fallback simple si el helper falla
                df_res['_sede_key'] = (df_res.get('nit_normalized', pd.Series([""]*len(df_res))).astype(str).fillna("") + "|" +
                                       df_res.get(dept_col, pd.Series([""]*len(df_res))).astype(str).fillna("") + "|" +
                                       df_res.get(mun_col, pd.Series([""]*len(df_res))).astype(str).fillna("")).astype(str)
            ctx['df_result'] = df_res
            try:
                st.sidebar.success(f"Clave _sede_key creada: {df_res['_sede_key'].nunique():,} claves únicas")
            except Exception:
                pass
    except Exception as _e:
        st.sidebar.warning(f"No fue posible asegurar _sede_key automáticamente: {_e}")
    # ---------------------

    # execute blocks
    ctx = _execute_blocks(ctx, folder)

    # After blocks executed, offer Excel export of collected outputs (if module available)
    try:
        # import locally to avoid import-time dependency if module absent
        from app.pagina import master_ips_export
        # show_export_button will render UI and allow user to download the workbook
        master_ips_export.show_export_button(ctx)
    except Exception as e:
        # do not raise—just inform in sidebar that export feature isn't available
        st.sidebar.info("Export to Excel not available." if e is None else f"Export to Excel not available: {e}")

    st.sidebar.success(f"Ejecutado hasta: {st.session_state.get('last_block','(none)')}")
    return ctx
'''

MASTER_05_PY = r'''# app/pagina/master_ips_05.py
"""
master_ips_05.py
Bloque 05: GIROS directos — resumen por NIT / Prestador

Esta versión:
 - Filtra giros usando sólo los NIT únicos presentes en ctx['df_result'] (respeta filtros).
 - Permite filtrar giros globalmente por EPS (selector "Filtrar giros por EPS").
 - Añade desplegable específico para el treemap con la lista de EPS detectadas
   (si se selecciona una EPS concreta el treemap muestra rectángulos por prestador;
    si se elige "TODAS" muestra jerarquía EPS -> Prestadores).
 - Control "Mostrar top N EPS en treemap (0 = todos)" para limitar EPS cuando se ve TODAS.
 - Muestra Top N prestadores en gráfico de barras (nombres, no NIT).
 - Presenta tabla ordenada descendente por monto girado (Valor girado en MM COP, sin decimales,
   con separadores de miles).
 - Respeta ctx['giro_path'], ctx['giro_date_range'] y usa helpers en ctx: load_giro_parquet, ensure_nit, find_col.
 - Guarda el DataFrame agregado en ctx['outputs']['giros_summary'] para uso posterior.
"""
from typing import Dict, Any
from pathlib import Path
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

def _fmt_millions_no_dec(x):
    try:
        if pd.isna(x):
            return "0"
        val = float(x)
        return "{:,.0f}".format(round(val))
    except Exception:
        return str(x)

def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    helpers = ctx.get("helpers", {})
    load_giro = helpers.get("load_giro_parquet")
    ensure_nit = helpers.get("ensure_nit")
    find_col = helpers.get("find_col")

    st.write("Bloque 05 — GIROS Directos por NIT / Prestador")

    df_result = ctx.get("df_result", pd.DataFrame()).copy()
    if df_result is None or df_result.empty:
        st.info("No hay datos filtrados (df_result vacío).")
        ctx.setdefault("outputs", {})["giros_summary"] = pd.DataFrame()
        return ctx

    # Asegurar nit_normalized en df_result
    try:
        if 'nit_normalized' not in df_result.columns:
            df_result = ensure_nit(df_result)
    except Exception:
        nit_guess = find_col(df_result, ["nit", "nit ips", "nit_prestador", "NIT"])
        if nit_guess and nit_guess in df_result.columns:
            df_result['nit_normalized'] = df_result[nit_guess].astype(str).str.replace(r"\D", "", regex=True).str.lstrip("0")
        else:
            df_result['nit_normalized'] = df_result.index.astype(str)

    nit_list = df_result['nit_normalized'].dropna().astype(str).unique().tolist()
    if len(nit_list) == 0:
        st.info("No se detectaron NITs únicos en los registros filtrados.")
        ctx.setdefault("outputs", {})["giros_summary"] = pd.DataFrame()
        return ctx

    giro_path = ctx.get("giro_path") or ""
    if not giro_path:
        st.info("No hay giro_path configurado (ctx['giro_path']).")
        ctx.setdefault("outputs", {})["giros_summary"] = pd.DataFrame()
        return ctx

    # Load giro dataset using helper
    try:
        giro_df = load_giro(giro_path) if load_giro else pd.DataFrame()
    except Exception as e:
        st.warning(f"Error cargando giros via helper: {e}")
        giro_df = pd.DataFrame()

    if giro_df is None or giro_df.empty:
        st.info("No se encontró datos de giros (giro.parquet vacío o no disponible).")
        ctx.setdefault("outputs", {})["giros_summary"] = pd.DataFrame()
        return ctx

    # Ensure nit_normalized in giro_df
    try:
        if 'nit_normalized' not in giro_df.columns:
            giro_df = ensure_nit(giro_df)
    except Exception:
        nit_guess = find_col(giro_df, ["nit", "nit ips", "nit_prestador", "NIT"])
        if nit_guess and nit_guess in giro_df.columns:
            giro_df['nit_normalized'] = giro_df[nit_guess].astype(str).str.replace(r"\D", "", regex=True).str.lstrip("0")
        else:
            giro_df['nit_normalized'] = giro_df.index.astype(str)

    # Detect amount column
    amount_col = find_col(giro_df, ["valor giro", "Valor Girado", "valor", "monto", "importe", "valor_total", "total"])
    if amount_col is None:
        numeric_cols = [c for c in giro_df.columns if pd.api.types.is_numeric_dtype(giro_df[c])]
        amount_col = numeric_cols[0] if numeric_cols else None
    if amount_col is None:
        st.info("No se detectó columna de monto en giros.")
        ctx.setdefault("outputs", {})["giros_summary"] = pd.DataFrame()
        return ctx

    # Detect EPS column
    eps_col = find_col(giro_df, ["EPS", "eps", "entidad", "pagador", "aseguradora", "entidad pagadora"])

    # Filter giro_df to only NITs present in df_result
    giro_df['nit_normalized'] = giro_df['nit_normalized'].astype(str)
    giro_filtered = giro_df[giro_df['nit_normalized'].isin([str(x) for x in nit_list])].copy()
    if giro_filtered.empty:
        st.info("No se encontraron giros para los NITs filtrados.")
        ctx.setdefault("outputs", {})["giros_summary"] = pd.DataFrame()
        return ctx

    # EPS selector (global filter for giros: applies to table and top-N graph)
    eps_values = []
    if eps_col and eps_col in giro_filtered.columns:
        eps_values = sorted(giro_filtered[eps_col].astype(str).fillna("").replace({"": None}).dropna().unique().tolist())
    eps_filter_options = ["TODAS"] + eps_values
    selected_eps_filter = st.selectbox("Filtrar giros por EPS (aplica a la tabla y gráfico)", options=eps_filter_options, index=0, key="block5_eps_filter")

    if selected_eps_filter and selected_eps_filter != "TODAS" and eps_col and eps_col in giro_filtered.columns:
        giro_filtered = giro_filtered[giro_filtered[eps_col].astype(str).str.strip() == str(selected_eps_filter).strip()]

    if giro_filtered.empty:
        st.info("No hay giros luego de aplicar filtro por EPS.")
        ctx.setdefault("outputs", {})["giros_summary"] = pd.DataFrame()
        return ctx

    # Date range filtering from ctx if present
    date_range = ctx.get("giro_date_range")
    if date_range and isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        date_col = find_col(giro_filtered, ["fecha", "fecha giro", "Fecha Giro", "fecha_giro", "fecha_pago", "date"])
        if date_col and date_col in giro_filtered.columns:
            try:
                giro_filtered['_parsed_fecha'] = pd.to_datetime(giro_filtered[date_col], errors='coerce')
                start_dt, end_dt = date_range
                if start_dt is not None and end_dt is not None:
                    mask = (giro_filtered['_parsed_fecha'] >= pd.to_datetime(start_dt)) & (giro_filtered['_parsed_fecha'] <= pd.to_datetime(end_dt))
                    giro_filtered = giro_filtered[mask].copy()
            except Exception:
                pass

    if giro_filtered.empty:
        st.info("No hay giros en el rango de fechas seleccionado.")
        ctx.setdefault("outputs", {})["giros_summary"] = pd.DataFrame()
        return ctx

    # Parse amount to numeric
    giro_filtered['_AMOUNT'] = pd.to_numeric(giro_filtered[amount_col].astype(str).str.replace(r"[^\d\-\.,]", "", regex=True).str.replace(",", "."), errors='coerce').fillna(0.0)

    # Provider name detection / mapping
    name_col_giro = find_col(giro_filtered, ["Nombre Prestador", "nombre prestador", "nombre_prestador", "NOMBRE PRESTADOR"])
    if name_col_giro and name_col_giro in giro_filtered.columns:
        giro_filtered['NOMBRE_PRESTADOR'] = giro_filtered[name_col_giro].astype(str).fillna("")
    else:
        name_col_df = find_col(df_result, ["nombre prestador", "razon social", "nombre", "nom_prestador", "nom prestador"])
        if name_col_df and name_col_df in df_result.columns:
            mapping = df_result.drop_duplicates(subset=['nit_normalized']).set_index('nit_normalized')[name_col_df].astype(str).to_dict()
            giro_filtered['NOMBRE_PRESTADOR'] = giro_filtered['nit_normalized'].map(lambda n: mapping.get(str(n), str(n)))
        else:
            giro_filtered['NOMBRE_PRESTADOR'] = giro_filtered['nit_normalized'].astype(str)

    # Aggregate by nit_normalized and provider name
    agg = giro_filtered.groupby(['nit_normalized','NOMBRE_PRESTADOR'], as_index=False)['_AMOUNT'].sum().rename(columns={'_AMOUNT':'VALOR_GIRADO_COP'})
    if agg.empty:
        st.info("No se pudo agregar giros por NIT.")
        ctx.setdefault("outputs", {})["giros_summary"] = pd.DataFrame()
        return ctx
    agg = agg.sort_values('VALOR_GIRADO_COP', ascending=False).reset_index(drop=True)
    agg['VALOR_GIRADO_MM'] = agg['VALOR_GIRADO_COP'] / 1_000_000.0
    agg['VALOR_GIRADO_MM_FMT'] = agg['VALOR_GIRADO_MM'].map(lambda x: _fmt_millions_no_dec(x))

    # Prepare display table
    display_table = agg.loc[:, ['nit_normalized','NOMBRE_PRESTADOR','VALOR_GIRADO_MM_FMT']].rename(columns={
        'nit_normalized':'NIT',
        'NOMBRE_PRESTADOR':'Nombre del prestador',
        'VALOR_GIRADO_MM_FMT':'Valor girado (MM COP)'
    }).reset_index(drop=True)

    # Title strings
    filters = ctx.get('filters', {}) or {}
    departamento = filters.get('Departamento') or "TODAS"
    municipio = filters.get('Municipio') or "TODAS"
    nivel = filters.get('Nivel') or "TODAS"
    servicio = filters.get('Servicio') or "TODAS"
    especialidad = filters.get('Especialidad') or "TODAS"

    # period string
    period_str = "Periodo analizado: (todas las fechas)"
    if date_range and isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        try:
            s,e = date_range
            s_str = pd.to_datetime(s).date().isoformat() if s is not None else ""
            e_str = pd.to_datetime(e).date().isoformat() if e is not None else ""
            period_str = f"Periodo analizado: {s_str} — {e_str}"
        except Exception:
            period_str = "Periodo analizado: (rango no disponible)"
    else:
        if '_parsed_fecha' in giro_filtered.columns and not giro_filtered['_parsed_fecha'].dropna().empty:
            try:
                mn = giro_filtered['_parsed_fecha'].min()
                mx = giro_filtered['_parsed_fecha'].max()
                period_str = f"Periodo analizado: {pd.to_datetime(mn).date().isoformat()} — {pd.to_datetime(mx).date().isoformat()}"
            except Exception:
                pass

    title_line1 = f"GIROS Directos recibidos — Departamento: {departamento}, Municipio: {municipio}, clínicas NIVEL: {nivel}"
    title_line2 = period_str
    title_line3 = f"Servicios: {servicio} — Especialidad: {especialidad}"

    st.markdown(f"### {title_line1}")
    st.markdown(f"**{title_line2}**")
    st.markdown(f"*{title_line3}*")

    # Plot top providers by VALOR_GIRADO_COP using Nombre del prestador labels
    max_bars = st.number_input("Máx filas en gráfico (Top N)", min_value=5, max_value=200, value=20, step=5, key="block5_top_n")
    plot_df = agg.head(int(max_bars)).copy()
    if not plot_df.empty:
        try:
            plot_df['label_mm'] = plot_df['VALOR_GIRADO_MM'].map(lambda x: _fmt_millions_no_dec(x) + " M")
            fig = px.bar(plot_df, x='VALOR_GIRADO_COP', y='NOMBRE_PRESTADOR', orientation='h',
                         labels={'VALOR_GIRADO_COP':'Valor girado (COP)', 'NOMBRE_PRESTADOR':'Prestador'},
                         text='label_mm', height=400)
            fig.update_traces(textposition='outside')
            fig.update_layout(yaxis={'automargin': True}, xaxis_tickformat=",.0f")
            st.subheader("Top prestadores por giros recibidos (COP)")
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.subheader("Top prestadores por giros recibidos (COP)")
            st.dataframe(plot_df[['nit_normalized','NOMBRE_PRESTADOR','VALOR_GIRADO_COP']].rename(columns={'nit_normalized':'NIT','NOMBRE_PRESTADOR':'Prestador','VALOR_GIRADO_COP':'Valor girado (COP)'}).head(int(max_bars)), use_container_width=True)
    else:
        st.info("No hay prestadores para graficar.")

    # Show the requested table ordered descending
    st.subheader("Tabla: GIROS Directos recibidos")
    st.dataframe(display_table, use_container_width=True)

    # ---------------- Treemap EPS -> Prestadores (mejorado con dropdown de EPS) ----------------
    st.subheader("Mapa de rectángulos: EPS → Prestadores (treemap)")

    try:
        treemap_df = giro_filtered.copy()
        if eps_col and eps_col in treemap_df.columns:
            treemap_df['EPS_USED'] = treemap_df[eps_col].astype(str).fillna("SIN_EPS")
        else:
            treemap_df['EPS_USED'] = "SIN_EPS"

        # Dropdown for treemap: explicit EPS selection (shows providers of that EPS)
        treemap_eps_options = ["TODAS"] + sorted(treemap_df['EPS_USED'].dropna().unique().tolist())
        treemap_eps_choice = st.selectbox("Seleccionar EPS para el treemap (TODAS = EPS → Prestadores)", options=treemap_eps_options, index=0, key="block5_treemap_eps_select")

        # Also keep the control to limit number of EPS shown when "TODAS" is chosen
        top_eps_n = st.number_input("Mostrar top N EPS en treemap (0 = todos)", min_value=0, max_value=200, value=0, step=1, key="block5_treemap_top_eps")

        if treemap_eps_choice and treemap_eps_choice != "TODAS":
            # show providers within the selected EPS
            sel = treemap_df[treemap_df['EPS_USED'] == treemap_eps_choice].copy()
            if sel.empty:
                st.info("No hay datos para el treemap (proveedores) en la EPS seleccionada.")
            else:
                agg_tm = sel.groupby('NOMBRE_PRESTADOR', as_index=False)['_AMOUNT'].sum().rename(columns={'_AMOUNT':'VALOR'})
                agg_tm['VALOR_MM'] = agg_tm['VALOR'] / 1_000_000.0
                fig_tm = px.treemap(agg_tm, path=['NOMBRE_PRESTADOR'], values='VALOR',
                                    color='VALOR', color_continuous_scale='Blues', custom_data=['VALOR_MM'])
                fig_tm.update_traces(texttemplate='%{label}<br>%{customdata[0]:,.0f} M', textposition='middle center',
                                     hovertemplate='<b>%{label}</b><br>Valor: %{value:,.0f} COP<extra></extra>')
                title_tm = f"Treemap — Prestadores en EPS: {treemap_eps_choice} — {title_line2}"
                fig_tm.update_layout(title=title_tm, margin=dict(t=40, l=10, r=10, b=10))
                st.plotly_chart(fig_tm, use_container_width=True)
        else:
            # TODAS: EPS -> Prestadores
            agg_tm = treemap_df.groupby(['EPS_USED','NOMBRE_PRESTADOR'], as_index=False)['_AMOUNT'].sum().rename(columns={'_AMOUNT':'VALOR'})
            if agg_tm.empty:
                st.info("No hay datos para generar el treemap EPS → Prestadores.")
            else:
                agg_tm['VALOR_MM'] = agg_tm['VALOR'] / 1_000_000.0
                if top_eps_n and top_eps_n > 0:
                    eps_totals = agg_tm.groupby('EPS_USED', as_index=False)['VALOR'].sum().sort_values('VALOR', ascending=False).head(top_eps_n)
                    eps_keep = eps_totals['EPS_USED'].tolist()
                    agg_tm = agg_tm[agg_tm['EPS_USED'].isin(eps_keep)]
                fig_tm = px.treemap(agg_tm, path=['EPS_USED','NOMBRE_PRESTADOR'], values='VALOR',
                                    color='VALOR', color_continuous_scale='Blues', custom_data=['VALOR_MM'])
                fig_tm.update_traces(texttemplate='%{label}<br>%{customdata[0]:,.0f} M', textposition='middle center',
                                     hovertemplate='<b>%{label}</b><br>Valor: %{value:,.0f} COP<extra></extra>')
                title_tm = f"Treemap EPS → Prestadores — {title_line2} — EPS seleccionada: TODAS"
                fig_tm.update_layout(title=title_tm, margin=dict(t=40, l=10, r=10, b=10))
                st.plotly_chart(fig_tm, use_container_width=True)

    except Exception as e:
        st.warning(f"No fue posible generar el treemap: {e}")

    # Save numeric result in context for downstream blocks
    ctx.setdefault("outputs", {})["giros_summary"] = agg

    return ctx
'''

MASTER_EXPORT_PY = r'''# app/pagina/master_ips_export.py
"""
master_ips_export.py

Exporter mejorado para MASTER IPS — genera un .xlsx en memoria con:
 - METADATA
 - Para cada DataFrame en ctx['outputs'] escribe:
     - <sheet> (RAW): datos sin transformar (preserva toda la información)
     - <sheet>_FORM: versión legible con números formateados (Miles/decimales)
 - DF_RESULT_preview (primera filas) si existe
 - Ajuste de ancho de columnas y freeze header
 - Aplicación de formatos numéricos si openpyxl está instalado

Uso:
  from app.pagina import master_ips_export
  master_ips_export.show_export_button(ctx)

Requisitos: pandas, openpyxl (opcional pero recomendado)
"""
from typing import Dict, Any
import io
import datetime
import pandas as pd
import numpy as np
import streamlit as st

try:
    import openpyxl
    from openpyxl.utils import get_column_letter
except Exception:
    openpyxl = None  # si no está, se seguirá generando el archivo pero sin formatos Excel avanzados


def _safe_sheet_name(name: str) -> str:
    s = str(name)[:31]
    for ch in [':', '\\', '/', '?', '*', '[', ']']:
        s = s.replace(ch, '_')
    return s


def _adjust_column_widths(ws, df: pd.DataFrame):
    """
    Ajusta anchos de columna en hoja openpyxl según contenido (limitar máximo razonable).
    """
    try:
        max_width = 50
        for i, col in enumerate(df.columns, start=1):
            col_letter = get_column_letter(i)
            # medir ancho teniendo en cuenta encabezado y algunas muestras
            try:
                # sample values: header + up to 100 filas
                sample_vals = [str(col)] + [str(v) for v in df[col].dropna().astype(str).head(100).tolist()]
                width = max(len(s) for s in sample_vals) + 2
                width = min(width, max_width)
                ws.column_dimensions[col_letter].width = width
            except Exception:
                continue
    except Exception:
        pass


def _apply_number_format_to_worksheet(ws, df: pd.DataFrame):
    """
    Aplica formato numérico (miles/decimales) a columnas numéricas en la hoja dada.
    """
    if openpyxl is None or df is None or df.empty:
        return
    nrows = df.shape[0]
    ncols = df.shape[1]
    if nrows == 0 or ncols == 0:
        return
    for j, col in enumerate(df.columns, start=1):
        try:
            is_num = pd.api.types.is_numeric_dtype(df[col])
        except Exception:
            is_num = False
        if not is_num:
            continue
        sample = df[col].dropna().head(20)
        has_decimal = False
        try:
            has_decimal = any(float(x) % 1 != 0 for x in sample.astype(float)) if not sample.empty else False
        except Exception:
            has_decimal = False
        fmt = '#,##0.00' if has_decimal else '#,##0'
        col_letter = get_column_letter(j)
        for i in range(2, 2 + nrows):
            cell = ws[f'{col_letter}{i}']
            try:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = fmt
            except Exception:
                continue


def _make_formatted_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve una copia 'formateada' para lectura humana:
    - columnas numéricas convertidas a strings con separadores de miles y 2 decimales cuando corresponde.
    - mantiene NaN como cadena vacía.
    """
    df_fmt = df.copy()
    num_cols = df_fmt.select_dtypes(include=[np.number]).columns.tolist()
    for c in num_cols:
        def fmt_val(x):
            try:
                if pd.isna(x):
                    return ""
                # Si el valor es entero (sin parte decimal significativa) mostramos sin decimales
                if float(x).is_integer():
                    return "{:,.0f}".format(int(round(float(x))))
                else:
                    return "{:,.2f}".format(float(x))
            except Exception:
                return str(x)
        df_fmt[c] = df_fmt[c].map(fmt_val)
    # Convertir tipos datetime a ISO
    dt_cols = df_fmt.select_dtypes(include=['datetime', 'datetimetz']).columns.tolist()
    for c in dt_cols:
        df_fmt[c] = df_fmt[c].dt.strftime('%Y-%m-%d %H:%M:%S').fillna("")
    return df_fmt


def build_excel_bytes_from_ctx(ctx: Dict[str, Any], include_formatted: bool = True) -> bytes:
    """
    Construye el workbook en memoria y devuelve bytes.
    Para cada DataFrame en ctx['outputs'] genera:
     - sheet RAW (datos sin modificar)
     - sheet FORM (si include_formatted True) con versión legible
    """
    outputs = ctx.get('outputs', {}) or {}
    buf = io.BytesIO()
    timestamp = datetime.datetime.now().isoformat(timespec='seconds')

    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        # METADATA
        metadata = {
            'generated_at': timestamp,
            'filters': str(ctx.get('filters', {})),
            'giro_path': str(ctx.get('giro_path', '')),
            'giro_date_range': str(ctx.get('giro_date_range', '')),
            'available_outputs': ", ".join(list(outputs.keys()))
        }
        md_df = pd.DataFrame(list(metadata.items()), columns=['key', 'value'])
        md_df.to_excel(writer, sheet_name=_safe_sheet_name('METADATA'), index=False)

        # Escribir cada output
        for key, val in outputs.items():
            sheet_base = _safe_sheet_name(str(key))
            try:
                if isinstance(val, pd.DataFrame):
                    df_full = val.copy()
                    # write RAW data
                    df_full.to_excel(writer, sheet_name=sheet_base, index=False)
                    # write formatted version for readability (if requested)
                    if include_formatted:
                        try:
                            df_fmt = _make_formatted_df(df_full)
                            sheet_fmt = _safe_sheet_name(f"{sheet_base}_FORM")
                            # if name clash ( > 31 chars ), ensure uniqueness by trimming
                            if sheet_fmt == sheet_base:
                                sheet_fmt = sheet_base + "_F"
                            df_fmt.to_excel(writer, sheet_name=sheet_fmt, index=False)
                        except Exception:
                            # si falla formateo, seguir adelante sin hoja FORM
                            pass
                else:
                    # no-DataFrame -> guardar su representación textual en una hoja
                    pd.DataFrame({str(key): [str(val)]}).to_excel(writer, sheet_name=sheet_base, index=False)
            except Exception as e:
                pd.DataFrame({'error': [str(e)]}).to_excel(writer, sheet_name=sheet_base, index=False)

        # Preview de df_result si existe (no truncar)
        try:
            df_result = ctx.get('df_result')
            if isinstance(df_result, pd.DataFrame) and not df_result.empty:
                preview = df_result.head(200).copy()
                preview.to_excel(writer, sheet_name=_safe_sheet_name('DF_RESULT_preview'), index=False)
        except Exception:
            pass

        # Post-procesado con openpyxl si está disponible
        if openpyxl is not None:
            try:
                wb = writer.book  # openpyxl workbook
                for key, val in outputs.items():
                    sheet_base = _safe_sheet_name(str(key))
                    # aplicar formato a la hoja RAW (si existe)
                    if sheet_base in wb.sheetnames and isinstance(val, pd.DataFrame) and not val.empty:
                        ws = wb[sheet_base]
                        _apply_number_format_to_worksheet(ws, val)
                        _adjust_column_widths(ws, val)
                        # freeze header row
                        ws.freeze_panes = "A2"
                    # aplicar anchos y freeze a la hoja FORM si existe
                    sheet_fmt = _safe_sheet_name(f"{sheet_base}_FORM")
                    if sheet_fmt in wb.sheetnames:
                        wsf = wb[sheet_fmt]
                        try:
                            # la hoja FORM fue escrita desde una DataFrame formateada
                            df_fmt = _make_formatted_df(val) if isinstance(val, pd.DataFrame) else None
                            if df_fmt is not None:
                                _adjust_column_widths(wsf, df_fmt)
                        except Exception:
                            _adjust_column_widths(wsf, val if isinstance(val, pd.DataFrame) else pd.DataFrame())
                        wsf.freeze_panes = "A2"
                # ajustar preview sheet si existe
                if 'DF_RESULT_preview' in wb.sheetnames:
                    ws_preview = wb['DF_RESULT_preview']
                    try:
                        _adjust_column_widths(ws_preview, df_result.head(200))
                        ws_preview.freeze_panes = "A2"
                    except Exception:
                        pass
                # Salvar workbook al buffer
                buf.seek(0)
                wb.save(buf)
            except Exception:
                # Si algo falla en el post-procesado, ignorar y devolver lo escrito por pandas
                pass

    buf.seek(0)
    return buf.read()


def show_export_button(ctx: Dict[str, Any], button_label: str = "Exportar todo a Excel (.xlsx)"):
    st.markdown("### Exportar contenidos")
    if st.button(button_label):
        with st.spinner("Generando archivo Excel..."):
            try:
                xbytes = build_excel_bytes_from_ctx(ctx, include_formatted=True)
                now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"master_ips_export_{now}.xlsx"
                st.download_button("Descargar Excel", data=xbytes, file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception as e:
                st.error(f"No fue posible generar el Excel: {e}")
'''

MASTER_WRAPPER_PY = r'''# app/pagina/master_ips.py
"""
Wrapper page for MASTER IPS.

This module is the page entrypoint used by main.py. It provides the run(filters, df_filtered, df_all)
function that the main dispatcher calls. It delegates the heavy work to app.pagina.master_ips_impl.run(...)
and then presents final UI/diagnostics, persists the context in session_state and exposes the
Excel export UI (if master_ips_export is available).
"""
from typing import Dict, Any, Optional
import importlib
import traceback

import streamlit as st
import pandas as pd

# Keep a short user-visible title for the page
st.set_page_config(page_title="MASTER IPS", layout="wide")

def _safe_list_outputs(ctx: Dict[str, Any]) -> Dict[str, int]:
    """Return a mapping output_key -> number of rows (or 0 if non-DataFrame)."""
    outs = {}
    for k, v in (ctx.get("outputs") or {}).items():
        try:
            if isinstance(v, pd.DataFrame):
                outs[k] = int(len(v))
            else:
                outs[k] = 1
        except Exception:
            outs[k] = 0
    return outs

def run(filters: dict, df_filtered: Optional[pd.DataFrame], df_all: Optional[pd.DataFrame]):
    """
    Entrypoint called by main.py.
    Signature preserved: run(filters, df_filtered, df_all)
    """
    st.title("MASTER IPS — Orquestador y ejecución completa")
    st.write("Este módulo ejecuta todos los sub-bloques del orquestador MASTER IPS y prepara los outputs para export/inspección.")

    # Import the implementation module that performs the block execution.
    try:
        impl = importlib.import_module("app.pagina.master_ips_impl")
    except Exception as e:
        st.error("No fue posible importar app.pagina.master_ips_impl. Revisa la traza:")
        st.exception(traceback.format_exc())
        return

    # Provide a visible button to (re)ejecutar todo — useful for interactive debugging.
    if "master_ips_last_run" not in st.session_state:
        st.session_state["master_ips_last_run"] = None

    col_run, col_info = st.columns([1, 3])
    with col_run:
        run_button = st.button("Ejecutar MASTER IPS (procesamiento 100%)", key="master_ips_run_button")
    with col_info:
        last = st.session_state.get("master_ips_last_run")
        if last:
            st.markdown(f"Última ejecución: {last}")

    # If the page was called from main.py automatically, run once automatically (to match previous behaviour).
    auto_run = True
    # If user explicitly presses the button, force a run.
    if run_button:
        auto_run = True

    if auto_run:
        st.info("Iniciando ejecución del orquestador. Esto ejecuta los bloques 01→05 en orden.")
        try:
            # Call the implementation. It must return the context dict (ctx).
            ctx = impl.run(filters, df_filtered, df_all)
            # If module returned None, attempt to retrieve ctx from impl (some versions may store state)
            if ctx is None:
                # fallback — try to get ctx from st.session_state if impl stored it there
                ctx = st.session_state.get("master_ips_ctx", {})
            if not isinstance(ctx, dict):
                st.warning("El orquestador no retornó un contexto válido (ctx). Se creará uno vacío.")
                ctx = {"outputs": {}}

            # Save context in session_state for downstream inspection
            st.session_state["master_ips_ctx"] = ctx
            st.session_state["master_ips_last_run"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

            # Summarize outputs
            outs_summary = _safe_list_outputs(ctx)
            if outs_summary:
                st.success("Procesamiento completado. Outputs generados:")
                for k, cnt in outs_summary.items():
                    st.write(f"- {k}: {cnt:,} filas (tipo: {'DataFrame' if isinstance(ctx['outputs'][k], pd.DataFrame) else type(ctx['outputs'][k]).__name__})")
            else:
                st.warning("Procesamiento finalizó pero no se detectaron salidas en ctx['outputs'].")

            # If specific expected outputs exist, show quick previews
            with st.expander("Previews de outputs (primeras 10 filas por hoja)"):
                for k, v in (ctx.get("outputs") or {}).items():
                    try:
                        if isinstance(v, pd.DataFrame):
                            st.markdown(f"**{k}** — {len(v):,} filas")
                            st.dataframe(v.head(10), use_container_width=True)
                        else:
                            st.markdown(f"**{k}** — (no-DataFrame): {str(v)[:200]}")
                    except Exception:
                        st.write(f"Imposible mostrar preview de {k}")

            # Offer export button if export module available
            try:
                export_mod = importlib.import_module("app.pagina.master_ips_export")
                if hasattr(export_mod, "show_export_button"):
                    st.markdown("---")
                    st.info("Generar export (Excel) con todos los outputs disponibles")
                    export_mod.show_export_button(ctx)
                else:
                    st.info("Módulo de export (master_ips_export) presente pero no expone show_export_button().")
            except Exception:
                st.info("Módulo master_ips_export no disponible — el export a Excel no está habilitado.")

            # Final confirmation
            st.success("MASTER IPS procesado 100% — revisa las secciones anteriores y descarga el Excel si lo deseas.")
        except Exception as e:
            st.error("Ocurrió un error durante la ejecución del orquestador MASTER IPS. Revisa la traza:")
            st.exception(traceback.format_exc())
            return

    # Provide a small utilities block: inspect ctx, clear ctx
    st.markdown("---")
    col_dbg_1, col_dbg_2 = st.columns([1,1])
    with col_dbg_1:
        if st.button("Mostrar ctx en session_state", key="master_ips_show_ctx"):
            st.json(st.session_state.get("master_ips_ctx", {}))
    with col_dbg_2:
        if st.button("Borrar ctx guardado", key="master_ips_clear_ctx"):
            st.session_state.pop("master_ips_ctx", None)
            st.success("Contexto guardado eliminado.")

    return  # page run ends here
'''

# REPLACE_CORE flag enabled to overwrite core files with above content
REPLACE_CORE = True

REPLACE_FILES = {
    "main.py": MAIN_PY,
    "app/pagina/master_ips_impl.py": MASTER_IMPL_PY,
    "app/pagina/master_ips_05.py": MASTER_05_PY,
    "app/pagina/master_ips_export.py": MASTER_EXPORT_PY,
    "app/pagina/master_ips.py": MASTER_WRAPPER_PY,
}

# --------------------------------------------------------------------

def run_cmd(cmd, cwd=None, check=True):
    print("> " + " ".join(cmd))
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0 and check:
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return res

def backup_project(root: Path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = root.parent / f"{root.name}_backup_{ts}.tar.gz"
    print(f"Creating full project backup at: {backup_name}")
    with tarfile.open(backup_name, "w:gz") as tar:
        tar.add(str(root), arcname=root.name)
    print("Backup created.")
    return backup_name

def move_to_orig(target: Path, dry_run=False):
    orig = target.with_name(target.stem + ".orig" + target.suffix)
    print(f"Will move {target} -> {orig}")
    if not dry_run:
        shutil.move(str(target), str(orig))
    return orig

def write_file(path: Path, content: str, dry_run=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        print(f"Backing up existing {path} -> {bak}")
        if not dry_run:
            shutil.copy2(str(path), str(bak))
    print(f"Writing {path} (dry_run={dry_run})")
    if not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

def ensure_git_init(root: Path, dry_run=False):
    if not (root / ".git").exists():
        print("Initializing git repository at", root)
        if not dry_run:
            run_cmd(["git", "init"], cwd=str(root))
    else:
        print("Git already initialized.")

def git_commit_all(root: Path, message: str, dry_run=False):
    print("Staging changes and committing...")
    if not dry_run:
        run_cmd(["git", "add", "."], cwd=str(root))
        run_cmd(["git", "commit", "-m", message], cwd=str(root), check=False)

def create_and_push_repo(root: Path, owner: str, repo: str, token: str, dry_run=False):
    if Github is None:
        raise RuntimeError("PyGithub not installed; install it if you want --push")
    g = Github(token)
    user = g.get_user()
    if owner and owner.lower() != user.login.lower():
        org = g.get_organization(owner)
        repo_obj = org.create_repo(name=repo, private=True)
        remote = repo_obj.clone_url
    else:
        repo_obj = user.create_repo(name=repo, private=True)
        remote = repo_obj.clone_url
    print("Created remote:", remote)
    if not dry_run:
        try:
            run_cmd(["git", "remote", "add", "origin", remote], cwd=str(root))
        except Exception:
            run_cmd(["git", "remote", "set-url", "origin", remote], cwd=str(root))
        run_cmd(["git", "checkout", "-B", "main"], cwd=str(root))
        run_cmd(["git", "push", "-u", "origin", "main"], cwd=str(root))

def default_wrapper_content(rel_path: str, orig_name: str) -> str:
    """
    Fallback wrapper content if no local wrapper is provided.
    """
    module_modname = Path(rel_path).stem
    return f'''# Auto-generated wrapper for {rel_path}
import importlib.util
import sys
from pathlib import Path
import streamlit as st
import pandas as pd
# Try to load original moved to .orig
orig_path = Path(__file__).with_name("{orig_name}")
spec = importlib.util.spec_from_file_location("{module_modname}_orig", str(orig_path))
orig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orig)
def _collect_outputs_from_module(mod):
    outputs = {{}}
    try:
        for k, v in getattr(mod, "__dict__", {{}}).items():
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
    ctx = {{"outputs": {{}}}}
    try:
        res = orig.run(*args, **kwargs)
    except Exception:
        res = None
    if isinstance(res, dict) and "outputs" in res:
        ctx = res
    else:
        ctx["outputs"].update(_collect_outputs_from_module(orig))
    try:
        st.session_state.setdefault("master_pages_outputs", {{}}).update(ctx.get("outputs", {{}}))
    except Exception:
        pass
    return ctx
'''

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default="C:/REPS", help="Path to project root")
    parser.add_argument("--push", action="store_true", help="Create remote GitHub repo and push (requires GITHUB_TOKEN)")
    parser.add_argument("--owner", help="GitHub owner for repo creation")
    parser.add_argument("--repo", help="GitHub repo name to create")
    parser.add_argument("--dry-run", action="store_true", help="Show actions but do not modify files or push")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    if not root.exists():
        print("Project root not found:", root)
        sys.exit(1)

    print("Project root:", root)
    if not args.yes:
        ans = input(f"Proceed to backup and apply wrappers and core replacements in {root}? (y/N): ").strip().lower()
        if ans not in ("y", "yes"):
            print("Aborted by user.")
            sys.exit(0)

    # Full backup
    backup_project(root)

    # 1) Move original files to .orig and write wrappers
    for rel in WRAP_FILES:
        target = root / rel
        if not target.exists():
            print(f"Target not found (skipping): {target}")
            continue
        orig = target.with_name(target.stem + ".orig" + target.suffix)
        print(f"Moving {target} -> {orig} (dry_run={args.dry_run})")
        if not args.dry_run:
            shutil.move(str(target), str(orig))
        # load wrapper content: prefer tools/wrappers/<filename> if exists, else use default fallback
        local_wrapper = LOCAL_WRAPPERS_DIR / Path(rel).name
        if local_wrapper.exists():
            content = local_wrapper.read_text(encoding="utf-8")
        else:
            content = default_wrapper_content(rel, orig.name)
        # Write wrapper back to target path
        write_file(target, content, dry_run=args.dry_run)

    # 2) Replace core files if REPLACE_CORE True and content provided in REPLACE_FILES
    if REPLACE_CORE:
        for rel, cont in REPLACE_FILES.items():
            target = root / rel
            if not cont:
                print(f"Replacement content for {rel} is empty; skipping.")
                continue
            write_file(target, cont, dry_run=args.dry_run)

    # 3) Ensure git, stage everything and commit
    ensure_git_init(root, dry_run=args.dry_run)
    git_commit_all(root, "Apply wrappers and core replacements (migration)", dry_run=args.dry_run)

    # 4) Optionally push to GitHub
    if args.push:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            print("GITHUB_TOKEN not set; cannot push.")
            sys.exit(1)
        owner = args.owner or os.environ.get("GITHUB_USER")
        repo = args.repo or root.name
        create_and_push_repo(root, owner, repo, token, dry_run=args.dry_run)

    print("Done. Inspect backups and .orig files before deleting anything.")

if __name__ == "__main__":
    main()
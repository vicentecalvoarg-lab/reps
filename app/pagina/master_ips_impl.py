# app/pagina/master_ips_impl.py
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

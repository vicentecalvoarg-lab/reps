"""
MASTER IPS - Implementación completa (heavy) para la página MASTER IPS.

Este archivo contiene:
 - Filtrado de la base maestra de IPS
 - Construcción de clave de sede
 - Cálculo de oferta por SERVICIO | ESPECIALIDAD (indicador por escala)
 - Integración con C:/REPS/data/sugeridos.csv para clasificación Alto/Normal/Bajo
 - Diagnóstico ligero (expander) para mapear combos no emparejados
 - Tabla detalle por sede, cálculo de giros por NIT y gráfico pie por combo
 - Treemap de giros y resumen por Grupo/NIT
 - Exportaciones Excel/CSV

Coloca este archivo en app/pagina/master_ips_impl.py y usa el wrapper ligero
app/pagina/master_ips.py que importa este módulo solo cuando se selecciona.
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import io
import re
import unicodedata
import difflib

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ---------------- Heurísticos / utilidades ----------------

def _clean_nit_str(s: Optional[str]) -> Optional[str]:
    if pd.isna(s) or s is None:
        return None
    s = str(s)
    cleaned = re.sub(r"\D", "", s)
    cleaned = cleaned.lstrip("0")
    return cleaned if cleaned != "" else None

def _normalize_name_for_match(s: Optional[str]) -> str:
    """Upper, strip, remove accents, unify separators and remove punctuation for matching."""
    if pd.isna(s) or s is None:
        return ""
    s = str(s).strip().upper()
    # Normalize accents
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # unify common separators to a single space (hyphen, pipe, en-dash, underscore)
    s = re.sub(r'[\|\-\–\—_]+', ' ', s)
    # remove everything except letters, numbers and spaces
    s = re.sub(r'[^A-Z0-9\s]', '', s)
    # compress spaces
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _find_column_like(df: pd.DataFrame, patterns: List[str]) -> Optional[str]:
    """Busca columnas por lista de patrones: exacto (case-insensitive) y contains."""
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

def _find_naturaleza_col(df: pd.DataFrame) -> Optional[str]:
    return _find_column_like(df, ["naturaleza", "naturaleza juridica", "naturaleza_juridica", "tipo prestador", "tipo", "NATURALEZA"])

def _find_nit_col(df: pd.DataFrame) -> Optional[str]:
    return _find_column_like(df, ["nit ips", "nit", "nit_prestador", "nit_prestador", "NIT"])

def _find_razon_social_col(df: pd.DataFrame) -> Optional[str]:
    return _find_column_like(df, ["razon social", "razon_social", "razon", "nombre prestador", "nombre_prestador", "grupo controlante"])

def _find_sede_col(df: pd.DataFrame) -> Optional[str]:
    return _find_column_like(df, ["nom sede ips", "nom sede", "nom_sede", "nombre sede", "nombre_sede", "nom_sede_ips"])

def _find_dept_col(df: pd.DataFrame) -> Optional[str]:
    return _find_column_like(df, ["departamento", "departamento_reg", "departamento_residencia", "NOMBRE DEPARTAMENTO", "Nombre departamento", "Departamento"])

def _find_mun_col(df: pd.DataFrame) -> Optional[str]:
    return _find_column_like(df, ["municipio", "NOMBRE MUNICIPIO", "Municipio", "Nombre municipio"])

def _find_level_col(df: pd.DataFrame) -> Optional[str]:
    return _find_column_like(df, ["nivel", "num nivel atencion", "num nivel", "nivel_atencion"])

def _find_service_group_col(df: pd.DataFrame) -> Optional[str]:
    return _find_column_like(df, ["nom grupo capacidad", "nom_grupo_capacidad", "grupo capacidad", "grupo_capacidad", "nom grupo", "servicio"])

def _find_service_desc_col(df: pd.DataFrame) -> Optional[str]:
    return _find_column_like(df, ["nom descripcion capacidad", "nom_descripcion_capacidad", "nom descripcion", "descripcion servicio", "descripcion", "especialidad"])

def _find_codigo_sede_cols(df: pd.DataFrame) -> List[str]:
    if df is None or df.columns is None:
        return []
    candidates = [c for c in df.columns if any(k in str(c).lower() for k in ("código sede", "codigo sede", "codigo_sede", "cod sede", "cod_sede", "numero sede", "nro sede", "número sede", "cod. sede"))]
    return candidates

def _ensure_nit_normalized(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "nit_normalized" in df.columns:
        return df
    nit_col = _find_nit_col(df)
    if nit_col is None:
        df["nit_normalized"] = pd.NA
        return df
    try:
        df["nit_normalized"] = df[nit_col].astype(str).apply(_clean_nit_str)
    except Exception:
        df["nit_normalized"] = df[nit_col].astype(str).str.replace(r"\D", "", regex=True).str.lstrip("0")
    return df

def _ensure_unique_column_names(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        new_cols = []
        for tup in df.columns:
            new_cols.append(" | ".join([str(x) for x in tup if x is not None]))
        df.columns = new_cols
    cols = [str(c) for c in df.columns.tolist()]
    seen = set()
    keep_idx = []
    dropped = []
    for i, c in enumerate(cols):
        if c in seen:
            dropped.append(c)
        else:
            seen.add(c)
            keep_idx.append(i)
    if dropped:
        df = df.iloc[:, keep_idx]
        st.warning(f"Se eliminaron columnas duplicadas por nombre: {', '.join(sorted(set(dropped)))}")
    df.columns = [str(c) for c in df.columns.tolist()]
    return df

def _safe_col_str(df_local: pd.DataFrame, col_name: str) -> pd.Series:
    """Devuelve columna como strings seguros, incluso si son multi-col."""
    if col_name is None or col_name not in df_local.columns:
        return pd.Series([""] * len(df_local), index=df_local.index)
    col_obj = df_local.loc[:, col_name]
    if isinstance(col_obj, pd.DataFrame):
        if col_obj.shape[1] == 1:
            s = col_obj.iloc[:, 0].astype(str)
        else:
            def _row_join(x):
                vals = ["" if pd.isna(v) else str(v) for v in x.tolist()]
                vals = [v.strip() for v in vals if v is not None and v not in ("", "nan", "None")]
                return " | ".join(vals)
            s = col_obj.apply(_row_join, axis=1)
    else:
        try:
            s = col_obj.astype(str)
        except Exception:
            s = col_obj.apply(lambda x: "" if pd.isna(x) else str(x))
    s = s.replace({"nan": "", "None": ""})
    return s.fillna("").astype(str)

# ---------------- Data loaders ----------------

@st.cache_data(show_spinner=False)
def load_giro_parquet(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
    except Exception:
        try:
            df = pd.read_parquet(path, engine="pyarrow")
        except Exception:
            return pd.DataFrame()
    return df

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
        {"sep": None, "engine": "python", "encoding": "latin1"},
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
        if df.shape[1] > 0:
            return df
    except Exception:
        pass
    return pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_sugeridos_csv(path: str) -> pd.DataFrame:
    """
    Carga sugeridos.csv con varios intentos de separador/encoding y devuelve DataFrame.
    """
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    attempts = [
        {"sep": ";", "encoding": "utf-8"},
        {"sep": ";", "encoding": "latin1"},
        {"sep": ",", "encoding": "utf-8"},
        {"sep": ",", "encoding": "latin1"},
        {"sep": None, "engine": "python", "encoding": "utf-8"},
        {"sep": None, "engine": "python", "encoding": "latin1"},
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
        if df.shape[1] > 0:
            return df
    except Exception:
        pass
    return pd.DataFrame()

# ---------------- Sede key builder ----------------

def _build_sede_keys_series(df_local: pd.DataFrame, codigo_cols: List[str], sede_name_col: Optional[str], dept_col: Optional[str], mun_col: Optional[str]) -> pd.Series:
    """
    Construye una clave por sede intentando:
     - códigos de sede (si existen)
     - nombre de sede
     - fallback: NIT|DEPARTAMENTO|MUNICIPIO
    """
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

# ---------------- Quantity detection helper ----------------

def _find_quantity_col(df: pd.DataFrame) -> Optional[str]:
    if df is None or df.columns is None:
        return None
    patterns = [
        "cantidad", "cant", "numero", "num", "oferta", "ofertados", "ofertada",
        "capacidad", "capacidad_total", "cantidad_ofertada", "n_camas", "nro", "nº",
        "n_cam", "camas", "num_camas", "cantidad camas", "cant_camas", "cantidad_oferta",
        "cantidad_oferta", "total_camas", "cupos", "puestos"
    ]
    for pat in patterns:
        col = _find_column_like(df, [pat])
        if col:
            return col
    return None

# ---------------- Services per scale (composite) ----------------

def render_services_per_scale_composite(df_source: pd.DataFrame, df_censo_path: str,
                                        service_col: Optional[str], specialty_col: Optional[str],
                                        dept_col: Optional[str], mun_col: Optional[str],
                                        escala: int = 100_000,
                                        applied_filters: Optional[Dict[str, str]] = None,
                                        giro_path: Optional[str] = None,
                                        giro_date_range: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None):
    """
    Genera la tabla por COMBO (SERVICIO | ESPECIALIDAD) con indicadores, y añade
    una clasificación sugerida comparando con C:/REPS/data/sugeridos.csv.
    """
    svc_col = service_col if (service_col and service_col in df_source.columns) else None
    spec_col = specialty_col if (specialty_col and specialty_col in df_source.columns) else None

    if svc_col is None and spec_col is None:
        st.info("No hay columna de servicio o especialidad detectada para calcular oferta/población.")
        return

    # construir COMBO
    df_src = df_source.copy()
    if svc_col and spec_col:
        df_src['COMBO'] = df_src[svc_col].astype(str).str.strip().fillna("") + " | " + df_src[spec_col].astype(str).str.strip().fillna("")
    elif svc_col:
        df_src['COMBO'] = df_src[svc_col].astype(str).str.strip().fillna("")
    else:
        df_src['COMBO'] = df_src[spec_col].astype(str).str.strip().fillna("")

    # construir clave de sede (vectorizada)
    codigo_cols = _find_codigo_sede_cols(df_src)
    df_src['_sede_key'] = _build_sede_keys_series(df_src, codigo_cols, sede_name_col=_find_sede_col(df_src), dept_col=dept_col, mun_col=mun_col)

    # contar sedes por COMBO
    df_sedes_unique = df_src.drop_duplicates(subset=['_sede_key', 'COMBO']).reset_index(drop=True)
    df_sedes_unique['COMBO_NORM'] = df_sedes_unique['COMBO'].astype(str).str.strip().replace({"nan": ""})
    sedes_counts = df_sedes_unique.groupby('COMBO_NORM', as_index=False)['_sede_key'].nunique().rename(columns={'_sede_key': 'SEDES_N'})

    # detectar columna de cantidad/oferta
    qty_col = _find_quantity_col(df_src)
    using_quantity = False
    total_offers = pd.DataFrame()
    per_sede_combo = pd.DataFrame()
    if qty_col:
        # normalizar y convertir a num en df_src; limpiamos caracteres no numéricos excepto . and ,
        try:
            cleaned = df_src[qty_col].astype(str).fillna("").str.replace(r"[^\d\-\.,]", "", regex=True)
            df_src['_QTY_NUM'] = pd.to_numeric(cleaned.str.replace(",", "."), errors='coerce').fillna(0.0)
            using_quantity = df_src['_QTY_NUM'].sum() > 0
        except Exception:
            df_src['_QTY_NUM'] = pd.to_numeric(df_src[qty_col].astype(str).str.replace(r"[^\d\-\.,]", "", regex=True).str.replace(",", "."), errors='coerce').fillna(0.0)
            using_quantity = df_src['_QTY_NUM'].sum() > 0

        if using_quantity:
            # sumar oferta por sede+combo (si hay múltiples filas por misma sede/combo)
            per_sede_combo = df_src.groupby(['_sede_key', 'COMBO'], as_index=False)['_QTY_NUM'].sum().rename(columns={'_QTY_NUM': 'OFERTA_POR_SEDE'})
            # luego total por combo
            total_offers = per_sede_combo.groupby('COMBO', as_index=False)['OFERTA_POR_SEDE'].sum().rename(columns={'OFERTA_POR_SEDE': 'TOTAL_OFERTA'})
            total_offers['COMBO_NORM'] = total_offers['COMBO'].astype(str).str.strip()
            total_offers = total_offers.loc[:, ['COMBO_NORM', 'TOTAL_OFERTA']]

    # If quantity not present, create per_sede_combo with OFERTA_POR_SEDE = 1 for presence
    if per_sede_combo.empty:
        per_sede_combo = df_src.drop_duplicates(subset=['_sede_key', 'COMBO']).loc[:, ['_sede_key', 'COMBO']].copy()
        per_sede_combo['OFERTA_POR_SEDE'] = 1.0

    # Merge sedes_counts and total_offers (if present)
    if not total_offers.empty:
        merged = sedes_counts.merge(total_offers, left_on='COMBO_NORM', right_on='COMBO_NORM', how='left')
        merged['TOTAL_OFERTA'] = merged['TOTAL_OFERTA'].fillna(0)
    else:
        merged = sedes_counts.copy()
        merged['TOTAL_OFERTA'] = merged['SEDES_N']

    counts = merged.rename(columns={'COMBO_NORM': 'COMBO'}).loc[:, ['COMBO', 'SEDES_N', 'TOTAL_OFERTA']].copy()

    # cargar censo y preparar (normalizando nombres)
    censo_df = load_censo_csv(df_censo_path)
    pop_map = {}
    mun_map = {}
    censo_work = pd.DataFrame()
    if censo_df is not None and not censo_df.empty:
        censo_dept_col = _find_column_like(censo_df, ["CÓDIGO DIVIPOLA", "Código DIVIPOLA", "CODIGO DIVIPOLA", "CÓDIGO", "Codigo", "NOMBRE DEPARTAMENTO", "departamento", "DEPARTAMENTO"])
        censo_mun_col = _find_column_like(censo_df, ["NOMBRE MUNICIPIO", "municipio", "MUNICIPIO", "NOMBRE_MUNICIPIO"])
        censo_total_col = _find_column_like(censo_df, ["TOTAL", "total", "POBLACION", "Poblacion", "TOTAL_POB", "TOTAL_POBLACION"])
        if censo_dept_col and censo_mun_col and censo_total_col:
            censo_work = censo_df[[censo_dept_col, censo_mun_col, censo_total_col]].copy()
            censo_work.columns = ["C_DEPT", "C_MUN", "C_TOTAL"]
            censo_work["C_DEPT_U"] = censo_work["C_DEPT"].astype(str).map(_normalize_name_for_match)
            censo_work["C_MUN_U"] = censo_work["C_MUN"].astype(str).map(_normalize_name_for_match)
            censo_work["C_TOTAL_NUM"] = pd.to_numeric(censo_work["C_TOTAL"].astype(str).str.replace(r"[^\d\-\.]", "", regex=True), errors="coerce").fillna(0).astype(float)
            censo_work = censo_work.drop_duplicates(subset=["C_DEPT_U", "C_MUN_U"])
            for _, r in censo_work.iterrows():
                pop_map.setdefault(r["C_DEPT_U"], {})[r["C_MUN_U"]] = r["C_TOTAL_NUM"]
            mun_map = censo_work.groupby("C_MUN_U")["C_TOTAL_NUM"].sum().to_dict()

    # Para cada combo, obtener municipios únicos y sumar población
    pops = []
    for combo in counts['COMBO'].tolist():
        s_rows = df_src[df_src['COMBO'].astype(str).str.strip() == combo]
        if 'DEPARTAMENTO' in s_rows.columns and 'MUNICIPIO' in s_rows.columns:
            depts = s_rows['DEPARTAMENTO'].astype(str).map(_normalize_name_for_match).fillna("")
            muns = s_rows['MUNICIPIO'].astype(str).map(_normalize_name_for_match).fillna("")
            pairs = pd.DataFrame({'D': depts, 'M': muns}).drop_duplicates()
        elif dept_col and mun_col and dept_col in df_source.columns and mun_col in df_source.columns:
            depts = s_rows[dept_col].astype(str).map(_normalize_name_for_match).fillna("")
            muns = s_rows[mun_col].astype(str).map(_normalize_name_for_match).fillna("")
            pairs = pd.DataFrame({'D': depts, 'M': muns}).drop_duplicates()
        else:
            pairs = pd.DataFrame(columns=['D', 'M'])

        pop_sum = 0.0
        if not pairs.empty and not censo_work.empty:
            for _, r in pairs.iterrows():
                D = r['D']
                M = r['M']
                val = pop_map.get(D, {}).get(M, None)
                if val is None:
                    val = mun_map.get(M, 0)
                pop_sum += float(val or 0)
        pops.append(pop_sum)

    counts['POBLACION'] = pops
    # Indicador calculado usando TOTAL_OFERTA
    counts['INDICADOR_POR_ESCALA'] = counts.apply(lambda r: (r['TOTAL_OFERTA'] / r['POBLACION'] * escala) if r['POBLACION'] > 0 else np.nan, axis=1)

    if counts.empty:
        st.info("No se encontraron servicios/especialidades para la selección actual.")
        return

    # Preparar display_df y ordenar por indicador descendente
    etiqueta_ind = f"OFERTA / {escala:,} hab."
    display_df = counts.copy()
    display_df = display_df.rename(columns={
        'COMBO': 'SERVICIO | ESPECIALIDAD',
        'SEDES_N': 'SEDES (n)',
        'TOTAL_OFERTA': 'TOTAL OFERTA'
    })
    display_df['POBLACION (hab)'] = display_df['POBLACION'].fillna(0).astype(float).round(0).map('{:,.0f}'.format)

    try:
        display_df['TOTAL_OFERTA_NUM'] = pd.to_numeric(display_df['TOTAL OFERTA'], errors='coerce').fillna(0.0)
    except Exception:
        display_df['TOTAL_OFERTA_NUM'] = display_df['SEDES (n)'].astype(float).fillna(0.0)

    display_df = display_df.sort_values('INDICADOR_POR_ESCALA', ascending=False).reset_index(drop=True)

    # ---------------- Load suggested benchmarks (sugeridos.csv) ----------------
    sugeridos_path = r"C:/REPS/data/sugeridos.csv"
    sugeridos_df = load_sugeridos_csv(sugeridos_path)
    if sugeridos_df is None:
        sugeridos_df = pd.DataFrame()

    # identificar columnas y construir SERVICE_U normalizado
    sug_keys = []
    if not sugeridos_df.empty:
        svc_col_sug = _find_column_like(sugeridos_df, ["Servicio Completo", "ServicioCompleto", "Servicio Completo (relacion servicio/especialidad)"])
        svc_col_alt = _find_column_like(sugeridos_df, ["Servicio", "Servico"])
        spec_col_alt = _find_column_like(sugeridos_df, ["Especialidad", "Especialidad REPS", "Especialidad"])
        if svc_col_sug:
            sugeridos_df['SERVICE_U'] = sugeridos_df[svc_col_sug].astype(str).map(_normalize_name_for_match)
        elif svc_col_alt:
            sugeridos_df['SERVICE_U'] = (sugeridos_df[svc_col_alt].astype(str).fillna("") + " - " + sugeridos_df[spec_col_alt].astype(str).fillna("")).map(_normalize_name_for_match)
        else:
            sugeridos_df['SERVICE_U'] = sugeridos_df.index.astype(str).map(_normalize_name_for_match)

        def _to_num(x):
            try:
                if pd.isna(x):
                    return np.nan
                s = str(x).strip()
                s = s.replace(".", "").replace(",", ".")
                s = re.sub(r"[^\d\.\-]", "", s)
                return float(s) if s not in ("", "nan") else np.nan
            except Exception:
                return np.nan

        min_col_sug = _find_column_like(sugeridos_df, ["Mínimo Recomendado", "Minimo Recomendado", "Mínimo Recomendado (por 100.000 hab.)"])
        umbral_col_sug = _find_column_like(sugeridos_df, ["Umbral Alto", "Umbral Alto (> por 100.000 hab.)", "Umbral"])
        sugeridos_df['MIN_RECO'] = sugeridos_df[min_col_sug].map(_to_num) if min_col_sug else np.nan
        sugeridos_df['UMBRAL_ALTO'] = sugeridos_df[umbral_col_sug].map(_to_num) if umbral_col_sug else np.nan

        sug_keys = sugeridos_df['SERVICE_U'].dropna().astype(str).unique().tolist()

    # helper: encontrar mejor clave sugerida (exact, contains, fuzzy)
    def _find_best_sugerido_key(combo_label: str, keys_list: List[str]) -> Optional[str]:
        if not combo_label or not keys_list:
            return None
        key = _normalize_name_for_match(combo_label)
        # exact normalized
        if key in keys_list:
            return key
        # contains
        for k in keys_list:
            if k and (k in key or key in k):
                return k
        # fuzzy suggestions
        candidates = difflib.get_close_matches(key, keys_list, n=3, cutoff=0.6)
        if candidates:
            return candidates[0]
        return None

    # apply automatic matching
    display_df['SUG_KEY_MATCH'] = display_df['SERVICIO | ESPECIALIDAD'].astype(str).map(lambda x: _find_best_sugerido_key(x, sug_keys) if sug_keys else None)
    display_df['SUG_MATCH_METHOD'] = display_df.apply(lambda r: ("exact" if (r['SUG_KEY_MATCH'] and _normalize_name_for_match(r['SERVICIO | ESPECIALIDAD'])==r['SUG_KEY_MATCH']) 
                                                            else ("contains" if r['SUG_KEY_MATCH'] and (r['SUG_KEY_MATCH'] in _normalize_name_for_match(r['SERVICIO | ESPECIALIDAD']) or _normalize_name_for_match(r['SERVICIO | ESPECIALIDAD']) in r['SUG_KEY_MATCH']) 
                                                                  else ("fuzzy" if r['SUG_KEY_MATCH'] else None))), axis=1)

    # Diagnóstico de no-match con sugerencias fuzzy (expander)
    with st.expander("Diagnóstico matching (sugeridos) — ver combos no emparejados y sugerencias"):
        st.write(f"Claves en sugeridos.csv: {len(sug_keys):,}")
        if not sugeridos_df.empty:
            st.dataframe(sugeridos_df.head(6))
        no_match = display_df[display_df['SUG_KEY_MATCH'].isna()]['SERVICIO | ESPECIALIDAD'].drop_duplicates().tolist()
        st.write(f"Combos sin match automático: {len(no_match):,}")
        if len(no_match) > 0:
            rows = []
            for combo in no_match[:200]:
                k_norm = _normalize_name_for_match(combo)
                sugg = difflib.get_close_matches(k_norm, sug_keys, n=5, cutoff=0.45) if len(sug_keys)>0 else []
                rows.append({"combo": combo, "norm": k_norm, "suggestions": sugg})
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            st.markdown("Si encuentras una sugerencia correcta, selecciona el combo abajo y asigna la clave sugerida.")
            selected_unmatched = st.selectbox("Combo no emparejado (para asignar manualmente)", options=["(ninguno)"] + no_match, key="diag_assign_one")
            if selected_unmatched and selected_unmatched != "(ninguno)":
                k_norm = _normalize_name_for_match(selected_unmatched)
                fuzzy_suggestions = difflib.get_close_matches(k_norm, sug_keys, n=10, cutoff=0.45) if len(sug_keys)>0 else []
                opts = ["(ninguno)"] + fuzzy_suggestions
                if len(opts)==1 and len(sug_keys)<=100:
                    opts = ["(ninguno)"] + sug_keys
                sel = st.selectbox(f"Asigna benchmark para: {selected_unmatched}", options=opts, key=f"assign_{_normalize_name_for_match(selected_unmatched)}")
                if sel and sel != "(ninguno)":
                    display_df.loc[display_df['SERVICIO | ESPECIALIDAD']==selected_unmatched, 'SUG_KEY_MATCH'] = sel
                    display_df.loc[display_df['SERVICIO | ESPECIALIDAD']==selected_unmatched, 'SUG_MATCH_METHOD'] = 'manual'
                    st.success(f"Asignado '{sel}' a '{selected_unmatched}'")

    # classification function using the found key
    def _classify_using_sugkey(indicator_value: float, sug_key: Optional[str]) -> str:
        if pd.isna(indicator_value):
            return "N/A"
        if not sug_key or sugeridos_df.empty:
            return "No benchmark"
        rec_row = sugeridos_df[sugeridos_df['SERVICE_U'] == sug_key]
        if rec_row.empty:
            return "No benchmark"
        rec = rec_row.iloc[0]
        min_reco = rec.get('MIN_RECO', np.nan)
        umbral = rec.get('UMBRAL_ALTO', np.nan)
        try:
            iv = float(indicator_value)
        except Exception:
            return "N/A"
        if not pd.isna(umbral) and iv >= umbral:
            return "Alto"
        if not pd.isna(min_reco) and iv >= min_reco:
            return "Normal"
        return "Bajo"

    # compute formatted indicator column and initial evaluation
    display_df['TOTAL OFERTA'] = display_df['TOTAL_OFERTA_NUM'].map(lambda x: f"{int(x):,}" if pd.notna(x) and float(x).is_integer() else (f"{x:,.2f}" if pd.notna(x) else "0"))
    display_df['SEDES (n)'] = display_df['SEDES (n)'].astype(int)
    display_df[etiqueta_ind] = display_df['INDICADOR_POR_ESCALA'].map(lambda x: "{:,.2f}".format(x) if pd.notna(x) else "N/A")
    display_df['EVALUACIÓN (sugerido)'] = display_df.apply(lambda r: _classify_using_sugkey(r['INDICADOR_POR_ESCALA'], r.get('SUG_KEY_MATCH')), axis=1)

    # Show table including the evaluation column
    st.subheader(f"Oferta por SERVICIO | ESPECIALIDAD por {escala:,} habitantes")
    st.write("Columnas: 'SEDES (n)' = número de sedes únicas; 'TOTAL OFERTA' = suma de la cantidad ofertada por sede (si existe). El indicador se calcula usando TOTAL OFERTA.")
    show_cols = ['SERVICIO | ESPECIALIDAD', 'SEDES (n)', 'TOTAL OFERTA', 'POBLACION (hab)', etiqueta_ind, 'EVALUACIÓN (sugerido)']
    st.dataframe(display_df.loc[:, show_cols].reset_index(drop=True), use_container_width=True)

    # ---------------- Selector: detalle por sede para la COMBO seleccionada ----------------
    try:
        combo_options = display_df['SERVICIO | ESPECIALIDAD'].astype(str).tolist()
        if combo_options:
            st.markdown("---")
            st.subheader("Detalle por sede para la combinación seleccionada")
            selected_combo = st.selectbox("Seleccionar SERVICIO | ESPECIALIDAD", options=["(ninguno)"] + combo_options, index=0)
            if selected_combo and selected_combo != "(ninguno)":
                per_sede_combo['COMBO_STR'] = per_sede_combo['COMBO'].astype(str).str.strip() if 'COMBO' in per_sede_combo.columns else per_sede_combo['COMBO'].astype(str).str.strip()
                selected_rows = per_sede_combo[per_sede_combo['COMBO_STR'] == selected_combo].copy() if 'COMBO_STR' in per_sede_combo.columns else per_sede_combo[per_sede_combo['COMBO'].astype(str).str.strip() == selected_combo].copy()

                sede_name_col = _find_sede_col(df_source)
                info_cols = ["nit_normalized"]
                if sede_name_col and sede_name_col in df_src.columns:
                    info_cols.append(sede_name_col)
                if dept_col and dept_col in df_src.columns:
                    info_cols.append(dept_col)
                if mun_col and mun_col in df_src.columns:
                    info_cols.append(mun_col)

                first_rows = df_src.drop_duplicates(subset=['_sede_key']).reset_index(drop=True)
                cols_to_take = ['_sede_key'] + [c for c in info_cols if c in first_rows.columns]
                first_rows_small = first_rows.loc[:, cols_to_take].copy()

                if not selected_rows.empty:
                    sel = selected_rows.merge(first_rows_small, on='_sede_key', how='left')

                    # --- robust giro per NIT calculation using same period filter (if provided) ---
                    nit_to_giros = {}
                    if giro_path:
                        giro_df = load_giro_parquet(giro_path)
                        if giro_df is not None and not giro_df.empty:
                            giro_df = _ensure_nit_normalized(giro_df)
                            amount_col = _find_column_like(giro_df, ["valor giro", "valor_giro", "valor", "monto", "monto_giro", "giro", "importe", "valor_total"])
                            date_col = _find_column_like(giro_df, ["fecha", "fecha giro", "fecha_giro", "fecha_pago", "date", "periodo"])
                            if date_col and date_col in giro_df.columns:
                                try:
                                    giro_df['_parsed_date'] = pd.to_datetime(giro_df[date_col], errors='coerce')
                                except Exception:
                                    giro_df['_parsed_date'] = pd.to_datetime(giro_df[date_col].astype(str), errors='coerce')
                                if giro_date_range and isinstance(giro_date_range, tuple) and len(giro_date_range) == 2:
                                    s_dt, e_dt = giro_date_range
                                    giro_df = giro_df[(giro_df['_parsed_date'] >= s_dt) & (giro_df['_parsed_date'] <= e_dt)]
                            if amount_col and amount_col in giro_df.columns:
                                giro_df['_amount'] = pd.to_numeric(giro_df[amount_col], errors='coerce').fillna(0.0)
                            else:
                                giro_df['_amount'] = 0.0
                            agg_giro = giro_df.groupby('nit_normalized', as_index=False)['_amount'].sum()
                            agg_giro['GIROS_MM_INT'] = (agg_giro['_amount'] / 1_000_000.0).round(0).fillna(0).astype(int)
                            agg_giro['nit_key'] = agg_giro['nit_normalized'].astype(str).map(lambda x: _clean_nit_str(x) or "")
                            nit_to_giros = dict(zip(agg_giro['nit_key'], agg_giro['GIROS_MM_INT'].astype(int)))

                    # Prepare display DataFrame
                    disp = sel.copy()
                    if 'nit_normalized' in disp.columns:
                        disp = disp.rename(columns={'nit_normalized': 'NIT'})
                    if sede_name_col and sede_name_col in disp.columns:
                        disp = disp.rename(columns={sede_name_col: 'NOMBRE SEDE'})
                    if dept_col and dept_col in disp.columns:
                        disp = disp.rename(columns={dept_col: 'DEPARTAMENTO'})
                    if mun_col and mun_col in disp.columns:
                        disp = disp.rename(columns={mun_col: 'MUNICIPIO'})
                    if 'OFERTA_POR_SEDE' in disp.columns:
                        disp = disp.rename(columns={'OFERTA_POR_SEDE': 'OFERTA POR SEDE'})

                    if 'NIT' in disp.columns:
                        disp['NIT_CLEAN'] = disp['NIT'].astype(str).map(lambda x: _clean_nit_str(x) or "")
                        disp['GIROS (MM COP)'] = disp['NIT_CLEAN'].map(lambda x: nit_to_giros.get(x, 0)).fillna(0).astype(int)
                    else:
                        disp['GIROS (MM COP)'] = 0

                    final_cols = []
                    if 'NIT' in disp.columns:
                        final_cols.append('NIT')
                    if 'NOMBRE SEDE' in disp.columns:
                        final_cols.append('NOMBRE SEDE')
                    elif '_sede_key' in disp.columns:
                        final_cols.append('_sede_key')
                    if 'OFERTA POR SEDE' in disp.columns:
                        final_cols.append('OFERTA POR SEDE')
                    final_cols.append('GIROS (MM COP)')
                    if 'DEPARTAMENTO' in disp.columns:
                        final_cols.append('DEPARTAMENTO')
                    if 'MUNICIPIO' in disp.columns:
                        final_cols.append('MUNICIPIO')

                    final_cols = [c for c in final_cols if c in disp.columns]

                    if 'OFERTA POR SEDE' in disp.columns:
                        disp['OFERTA POR SEDE'] = pd.to_numeric(disp['OFERTA POR SEDE'], errors='coerce').fillna(0)
                    if 'GIROS (MM COP)' in disp.columns:
                        disp['GIROS (MM COP)'] = pd.to_numeric(disp['GIROS (MM COP)'], errors='coerce').fillna(0).astype(int)

                    if 'OFERTA POR SEDE' in disp.columns:
                        disp_show = disp.loc[:, final_cols].sort_values('OFERTA POR SEDE', ascending=False).reset_index(drop=True)
                    else:
                        disp_show = disp.loc[:, final_cols].sort_values('GIROS (MM COP)', ascending=False).reset_index(drop=True)

                    st.dataframe(disp_show, use_container_width=True)

    except Exception as e:
        st.error(f"Error preparando selector de sedes: {e}")

    # ---------------- Treemap de giros (si se dispone de giro.parquet) ----------------
    st.markdown("---")
    st.header("Giros ADRES (integrado) — Treemap y resumen por Grupo / NIT")

    giro_df = pd.DataFrame()
    if giro_path:
        giro_df = load_giro_parquet(giro_path)
    if giro_df is None or giro_df.empty:
        st.warning(f"No se encontró {giro_path} o está vacío. No se mostrará treemap de giros.")
    else:
        # detectar columnas relevantes
        date_col = _find_column_like(giro_df, ["fecha", "fecha giro", "fecha_giro", "fecha_pago", "date", "periodo"])
        amount_col = _find_column_like(giro_df, ["valor giro", "valor_giro", "valor", "monto", "monto_giro", "giro", "importe", "valor_total", "total"])
        razon_col_giro = _find_column_like(giro_df, ["razon social", "razon_social", "razon", "grupo controlante", "nombre prestador"])

        # aplicar filtro por periodo si se indicó
        if date_col and giro_date_range:
            try:
                giro_df['_parsed_date'] = pd.to_datetime(giro_df[date_col], errors='coerce')
                s_dt, e_dt = giro_date_range
                giro_df = giro_df[(giro_df['_parsed_date'] >= s_dt) & (giro_df['_parsed_date'] <= e_dt)]
            except Exception:
                pass

        # si no se detectó amount_col, intentar heurísticas alternativas
        if not amount_col:
            # buscar columnas con palabras clave
            lower_cols = [str(c).lower() for c in giro_df.columns]
            for keyword in ("valor", "monto", "importe", "total", "amount", "valor_total"):
                for i, c in enumerate(lower_cols):
                    if keyword in c:
                        amount_col = giro_df.columns[i]
                        break
                if amount_col:
                    break
        # fallback: primer columna numérica plausible
        if not amount_col:
            numeric_cols = [c for c in giro_df.columns if pd.api.types.is_numeric_dtype(giro_df[c])]
            if numeric_cols:
                amount_col = numeric_cols[0]

        # si tras heurísticas no hay columna de monto, avisar y salir
        if not amount_col:
            st.warning("No se detectó ninguna columna con montos en giro.parquet; el treemap requiere una columna numérica de valor. Revisa el archivo.")
        else:
            # crear columnas necesarias
            giro_filtered = _ensure_nit_normalized(giro_df.copy())
            try:
                giro_filtered['_amount'] = pd.to_numeric(giro_filtered[amount_col], errors='coerce').fillna(0.0)
            except Exception:
                giro_filtered['_amount'] = 0.0
            giro_filtered['_nit_norm'] = giro_filtered['nit_normalized'].astype(str).fillna("")

            # determinar columna de nombre/razón social a usar como grupo
            if razon_col_giro and razon_col_giro in giro_filtered.columns:
                giro_filtered['_grupo_raw'] = giro_filtered[razon_col_giro].astype(str).fillna("Sin grupo")
            else:
                # intentar otras opciones (ej: nombre prestador)
                alt = _find_column_like(giro_filtered, ["nombre prestador", "nombre_prestador", "razon", "proveedor", "prestador"])
                giro_filtered['_grupo_raw'] = giro_filtered[alt].astype(str).fillna("Sin grupo") if alt else "Sin grupo"

            # asignar grupo por NIT si es posible (mapear desde df_src)
            nit_to_group = {}
            try:
                razon_col_local = _find_razon_social_col(df_source) or _find_sede_col(df_source)
                nit_col_local = 'nit_normalized' if 'nit_normalized' in df_src.columns else (_find_nit_col(df_source) or "")
                if nit_col_local and nit_col_local in df_src.columns and razon_col_local and razon_col_local in df_src.columns:
                    tmp_map = df_src.loc[:, [nit_col_local, razon_col_local]].dropna(subset=[nit_col_local]).copy()
                    tmp_map['NIT_norm'] = tmp_map[nit_col_local].astype(str).map(_clean_nit_str)
                    tmp_map = tmp_map.drop_duplicates(subset=['NIT_norm'], keep='first')
                    nit_to_group = dict(zip(tmp_map['NIT_norm'].astype(str), tmp_map[razon_col_local].astype(str)))
            except Exception:
                nit_to_group = {}

            def _assign_group(row):
                n = str(row.get('_nit_norm', ''))
                if n and n in nit_to_group and nit_to_group[n]:
                    return nit_to_group[n]
                return row.get('_grupo_raw', "Sin grupo")

            giro_filtered['_grupo_assigned'] = giro_filtered.apply(_assign_group, axis=1)

            agg = giro_filtered.groupby(['_grupo_assigned', '_nit_norm'], as_index=False)['_amount'].sum()
            agg['GIROS_MM'] = (agg['_amount'] / 1_000_000.0).round(2)

            if agg.empty:
                st.info("No hay giros válidos (monto=0 o filtrado por fecha). No se mostrará treemap.")
            else:
                group_sum = agg.groupby('_grupo_assigned', as_index=False)['GIROS_MM'].sum().rename(columns={'GIROS_MM': 'GRUPO_GIROS_MM'})
                treemap_df = agg.merge(group_sum, on='_grupo_assigned', how='left')

                st.subheader("Treemap de giros (MM COP) — Grupos y NITs")
                try:
                    fig = px.treemap(treemap_df, path=['_grupo_assigned', '_nit_norm'], values='GIROS_MM', color='GIROS_MM', color_continuous_scale=px.colors.sequential.Greens)
                    fig.update_layout(margin=dict(t=40, l=10, r=10, b=10))
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Error generando treemap: {e}")

                st.subheader("Resumen de giros por Grupo y NIT (MM COP)")
                table_display = treemap_df[['_grupo_assigned', '_nit_norm', 'GIROS_MM']].rename(columns={'_grupo_assigned': 'GRUPO CONTROLANTE', '_nit_norm': 'NIT', 'GIROS_MM': 'GIROS (MM COP)'}).sort_values('GIROS (MM COP)', ascending=False).reset_index(drop=True)
                try:
                    table_display['GIROS (MM COP)'] = pd.to_numeric(table_display['GIROS (MM COP)'], errors='coerce').fillna(0)
                    st.dataframe(table_display, use_container_width=True)
                except Exception:
                    st.dataframe(table_display, use_container_width=True)

    # ---------------- Export buttons ----------------
    st.markdown("---")
    st.write("Exportar resultados")
    if st.button("Exportar oferta (Excel)"):
        try:
            out_buf = io.BytesIO()
            export_df = display_df.copy()
            with pd.ExcelWriter(out_buf, engine="openpyxl") as writer:
                export_df.to_excel(writer, sheet_name="oferta_por_escala", index=False)
            out_buf.seek(0)
            st.download_button("Descargar Excel oferta_por_escala.xlsx", data=out_buf, file_name="oferta_por_escala.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.error(f"Error exportando oferta: {e}")

    if not sugeridos_df.empty:
        if st.button("Exportar sugeridos (Excel)"):
            try:
                out_buf = io.BytesIO()
                with pd.ExcelWriter(out_buf, engine="openpyxl") as writer:
                    sugeridos_df.to_excel(writer, sheet_name="sugeridos", index=False)
                out_buf.seek(0)
                st.download_button("Descargar sugeridos.xlsx", data=out_buf, file_name="sugeridos.xlsx", mime="application/vnd.openxmlformats-officedocument-spreadsheetml.sheet")
            except Exception as e:
                st.error(f"Error exportando sugeridos: {e}")

# ---------------- Page entrypoint ----------------

def run(filters: Dict[str, Any], df_filtered: pd.DataFrame, df_all: pd.DataFrame):
    """
    Entrypoint público: esta función será llamada por el wrapper master_ips.py
    """
    st.title("MASTER IPS — Filtrado y tabla de identificación")
    st.markdown("**Determinación de Niveles de Complejidad en IPS**")
    if df_all is None or df_all.empty:
        st.error("No hay datos cargados (df_all vacío).")
        return

    # normalize input
    df = df_all.copy()
    df = _ensure_nit_normalized(df)

    # detect columns
    nit_col = _find_nit_col(df)
    razon_col = _find_razon_social_col(df)
    sede_col = _find_sede_col(df)
    dept_col = _find_dept_col(df)
    mun_col = _find_mun_col(df)
    level_col = _find_level_col(df)
    naturaleza_col = _find_naturaleza_col(df)
    service_group_col = _find_service_group_col(df)
    service_desc_col = _find_service_desc_col(df)

    # Sidebar filters (idénticos a lo usado antes)
    st.sidebar.header("Filtros principales")
    nivel_options = ["TODAS", "1", "2", "3"]
    selected_nivel = st.sidebar.selectbox("Nivel", options=nivel_options, index=0)

    dept_values = []
    if dept_col and dept_col in df.columns:
        dept_values = sorted(df[dept_col].dropna().astype(str).unique().tolist())
    selected_dept = st.sidebar.selectbox("Departamento", options=["TODAS"] + dept_values, index=0)

    mun_values = []
    if mun_col and mun_col in df.columns:
        if selected_dept and selected_dept != "TODAS":
            mun_values = sorted(df[df[dept_col].astype(str) == str(selected_dept)][mun_col].dropna().astype(str).unique().tolist())
        else:
            mun_values = sorted(df[mun_col].dropna().astype(str).unique().tolist())
    selected_mun = st.sidebar.selectbox("Municipio", options=["TODAS"] + mun_values, index=0)

    naturaleza_values = []
    if naturaleza_col and naturaleza_col in df.columns:
        naturaleza_values = sorted(df[naturaleza_col].dropna().astype(str).unique().tolist())
    selected_naturaleza = st.sidebar.selectbox("Naturaleza", options=["TODAS"] + naturaleza_values, index=0)

    service_values = []
    if service_group_col and service_group_col in df.columns:
        service_values = sorted(df[service_group_col].dropna().astype(str).unique().tolist())
    selected_service = st.sidebar.selectbox("Servicio", options=["TODAS"] + service_values, index=0)

    especialidad_values = []
    if service_desc_col and service_desc_col in df.columns:
        especialidad_values = sorted(df[service_desc_col].dropna().astype(str).unique().tolist())
    selected_especialidad = st.sidebar.selectbox("Especialidad", options=["TODAS"] + especialidad_values, index=0)

    st.sidebar.markdown("---")
    max_rows = st.sidebar.number_input("Máx filas a mostrar", min_value=10, max_value=100000, value=500, step=10)
    show_preview = st.sidebar.checkbox("Mostrar preview (primeras N filas)", value=True)

    escala_choice = st.sidebar.selectbox("Escala indicador", options=[("Por 1.000",1000),("Por 10.000",10000),("Por 100.000",100000)], format_func=lambda x: x[0], index=2)
    ESCALA = escala_choice[1]

    # Filtro periodo giros (si gira.parquet está disponible)
    giro_path = r"C:/REPS/data/giro.parquet"
    date_range = None
    giro_tmp = load_giro_parquet(giro_path)
    if giro_tmp is not None and not giro_tmp.empty:
        date_col_tmp = _find_column_like(giro_tmp, ["fecha", "fecha giro", "fecha_giro", "fecha_pago", "date", "periodo"])
        if date_col_tmp and date_col_tmp in giro_tmp.columns:
            try:
                giro_tmp['_parsed_date_tmp'] = pd.to_datetime(giro_tmp[date_col_tmp], errors='coerce')
                min_date = giro_tmp['_parsed_date_tmp'].min()
                max_date = giro_tmp['_parsed_date_tmp'].max()
                if not pd.isna(min_date) and not pd.isna(max_date):
                    default_start = max_date - pd.DateOffset(months=12) if (max_date - min_date).days > 30 else min_date
                    start_date, end_date = st.sidebar.date_input("Periodo giros (desde - hasta)", value=(default_start.date(), max_date.date()))
                    try:
                        date_range = (pd.to_datetime(start_date), pd.to_datetime(end_date))
                    except Exception:
                        date_range = None
            except Exception:
                pass
        else:
            st.sidebar.info("No se detectó columna fecha en giro.parquet; no habrá filtro por periodo para giros.")

    # Aplicar filtros al df_result
    df_result = df.copy()
    if level_col and level_col in df_result.columns and selected_nivel != "TODAS":
        df_result = df_result[df_result[level_col].astype(str) == str(selected_nivel)]
    if dept_col and dept_col in df_result.columns and selected_dept != "TODAS":
        df_result = df_result[df_result[dept_col].astype(str) == str(selected_dept)]
    if mun_col and mun_col in df_result.columns and selected_mun != "TODAS":
        df_result = df_result[df_result[mun_col].astype(str) == str(selected_mun)]
    if naturaleza_col and naturaleza_col in df_result.columns and selected_naturaleza != "TODAS":
        df_result = df_result[df_result[naturaleza_col].astype(str) == str(selected_naturaleza)]
    if service_group_col and service_group_col in df_result.columns and selected_service != "TODAS":
        df_result = df_result[df_result[service_group_col].astype(str) == str(selected_service)]
    if service_desc_col and service_desc_col in df_result.columns and selected_especialidad != "TODAS":
        df_result = df_result[df_result[service_desc_col].astype(str) == str(selected_especialidad)]

    st.write(f"Filas luego de aplicar filtros: {len(df_result):,}")

    # Construir tabla identificación por sede y mostrar
    id_cols_map: Dict[str, str] = {}
    id_cols_map["NIT"] = "nit_normalized" if "nit_normalized" in df_result.columns else (nit_col if nit_col and nit_col in df_result.columns else "nit_normalized")
    if razon_col and razon_col in df_result.columns:
        id_cols_map["RAZON SOCIAL"] = razon_col
    if sede_col and sede_col in df_result.columns:
        id_cols_map["NOMBRE SEDE"] = sede_col
    if dept_col and dept_col in df_result.columns:
        id_cols_map["DEPARTAMENTO"] = dept_col
    if mun_col and mun_col in df_result.columns:
        id_cols_map["MUNICIPIO"] = mun_col
    if level_col and level_col in df_result.columns:
        id_cols_map["NIVEL"] = level_col

    preferred_order = ["NIT", "NOMBRE SEDE", "DEPARTAMENTO", "MUNICIPIO", "NIVEL", "RAZON SOCIAL"]
    display_cols: List[str] = []
    display_col_names: Dict[str, str] = {}
    for k in preferred_order:
        src = id_cols_map.get(k)
        if src and src in df_result.columns and src not in display_cols:
            display_cols.append(src)
            display_col_names[src] = k
    if "NIT" not in display_col_names.values():
        if id_cols_map.get("NIT") and id_cols_map["NIT"] in df_result.columns:
            src = id_cols_map["NIT"]
            if src not in display_cols:
                display_cols.insert(0, src)
                display_col_names[src] = "NIT"

    id_table = pd.DataFrame()
    if display_cols:
        tmp = df_result.loc[:, display_cols + ["nit_normalized"]].copy()
        codigo_cols = _find_codigo_sede_cols(df_result)
        sede_name_col = id_cols_map.get("NOMBRE SEDE", None)

        tmp['_sede_key'] = ""
        for c in codigo_cols:
            if c in tmp.columns:
                s = _safe_col_str(tmp, c).str.strip()
                mask = tmp['_sede_key'].astype(str) == ""
                tmp.loc[mask & (s != ""), '_sede_key'] = s[mask & (s != "")]
        if sede_name_col and sede_name_col in tmp.columns:
            s_sede = _safe_col_str(tmp, sede_name_col).str.strip()
            mask = tmp['_sede_key'].astype(str) == ""
            tmp.loc[mask & (s_sede != ""), '_sede_key'] = s_sede[mask & (s_sede != "")]
        mask = tmp['_sede_key'].astype(str) == ""
        nit_s = _safe_col_str(tmp, "nit_normalized")
        dept_s = _safe_col_str(tmp, dept_col) if dept_col else pd.Series([""] * len(tmp), index=tmp.index)
        mun_s = _safe_col_str(tmp, mun_col) if mun_col else pd.Series([""] * len(tmp), index=tmp.index)
        fallback = nit_s.fillna("").astype(str) + "|" + dept_s.fillna("").astype(str) + "|" + mun_s.fillna("").astype(str)
        tmp.loc[mask, '_sede_key'] = fallback[mask]
        tmp['_sede_key'] = tmp['_sede_key'].astype(str)

        tmp_unique = tmp.drop_duplicates(subset=["_sede_key"], keep="first").reset_index(drop=True)
        id_table = tmp_unique.loc[:, display_cols].rename(columns=display_col_names)

        if "RAZON SOCIAL" in id_table.columns:
            id_table = id_table.rename(columns={"RAZON SOCIAL": "GRUPO CONTROLANTE"})

        desired_order = ["NIT", "NOMBRE SEDE", "DEPARTAMENTO", "MUNICIPIO", "NIVEL"]
        final_cols = [c for c in desired_order if c in id_table.columns]
        if "GRUPO CONTROLANTE" in id_table.columns:
            final_cols.append("GRUPO CONTROLANTE")
        final_cols += [c for c in id_table.columns if c not in final_cols]
        id_table = id_table.loc[:, final_cols]
        id_table = _ensure_unique_column_names(id_table)

        for c in id_table.columns:
            col_obj = id_table.loc[:, c]
            if isinstance(col_obj, pd.DataFrame):
                try:
                    id_table[c] = col_obj.astype(str).apply(lambda x: " | ".join(x.dropna().astype(str)), axis=1)
                except Exception:
                    id_table[c] = col_obj.astype(str)
                continue
            try:
                if pd.api.types.is_object_dtype(col_obj.dtype):
                    id_table[c] = col_obj.astype(str).fillna("")
                elif pd.api.types.is_integer_dtype(col_obj.dtype) or pd.api.types.is_float_dtype(col_obj.dtype):
                    id_table[c] = pd.to_numeric(col_obj, errors='coerce').fillna(0)
                else:
                    id_table[c] = col_obj.astype(str).fillna("")
            except Exception:
                id_table[c] = id_table[c].astype(str).fillna("")

    # mostrar tabla id_table
    st.subheader("Tabla de identificación (un registro por sede)")
    if id_table is None or id_table.empty:
        st.info("No se encontraron filas para mostrar.")
    else:
        st.write(f"Columnas mostradas: {', '.join(id_table.columns.tolist())}")
        if show_preview:
            id_table_to_show = _ensure_unique_column_names(id_table)
            st.dataframe(id_table_to_show.head(int(max_rows)), use_container_width=True)

    # finalmente, renderizamos la tabla de servicios por escala con la función compuesta
    try:
        render_services_per_scale_composite(df_result, r"C:/REPS/data/censo.csv", service_group_col, service_desc_col, dept_col, mun_col, escala=ESCALA, applied_filters=None, giro_path=giro_path, giro_date_range=date_range)
    except Exception as e:
        st.error(f"Error calculando oferta por escala: {e}")
"""
Comparaciones de IPS - Módulo de comparación por NIT de referencia (entrada manual).
Interfaz:
    run(filtered_df: pd.DataFrame, nits_display: list, df_all: pd.DataFrame, filters: dict)
Funcionalidades:
 - Entrada manual de NIT (sin separadores).
 - Identificación automática del nombre de la IPS y de la sede.
 - Muestra un listado "IPS analizadas" con NIT, Nombre sede, Nivel, Departamento, Municipio.
 - Usa los nombres para etiquetar la tabla comparativa, KPI y gráficas.
 - Selección robusta de peers: filtra por nivel y geo, rankea por similitud cuantitativa (sedes, servicios, capacidad).
 - Agrega tabla con datos del gráfico "Top servicios: Usuarios diarios por servicio (Referencia vs Peers)".
 - Permite entrada manual de NITs de peers a comparar, combinada con selección automática.
 - Agrega menú desplegable para seleccionar servicio en el gráfico y tabla de Top servicios.
 - Título del gráfico: "Comparación IPS con {nombre IPS referencia}" y fuente "REPS".
 - Permite seleccionar sede específica de la referencia o "Todas" para consolidar.
 - Checkbox para consolidar capacidad de peers (sumar sedes) o usar sedes individuales.
"""
from typing import List, Dict
import traceback
import re
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# Optional imports from the project; if missing, we'll fallback gracefully.
try:
    from app.data import explode_nits_regex
except Exception:
    explode_nits_regex = None
try:
    from app.standards import find_standard_for_service
except Exception:
    def find_standard_for_service(x):
        return None
try:
    from app.utils import hash_seed, format_number
except Exception:
    def hash_seed(*args, **kwargs):
        return abs(hash(tuple(args))) % (2**32)
    def format_number(x):
        try:
            return f"{int(x):,}"
        except Exception:
            return str(x)
try:
    from app.components import tables as tables_comp
except Exception:
    tables_comp = None

# ---------------- Helpers ----------------
def _clean_nit_str(s):
    if pd.isna(s) or s is None:
        return None
    s = str(s)
    cleaned = re.sub(r'\D', '', s)
    cleaned = cleaned.lstrip('0')
    return cleaned if cleaned != '' else None

def _find_name_column(df: pd.DataFrame) -> str:
    candidates = [
        'Nombre prestador', 'Nombre_Prestador', 'nombre prestador', 'nom sede IPS', 'nom_sede_IPS',
        'nom sede', 'nom_sede', 'Nombre', 'nombre_prestador', 'Nombre prestador'
    ]
    for cand in candidates:
        for col in df.columns:
            if col.lower() == cand.lower():
                return col
    for col in df.columns:
        if 'nombre' in col.lower() and 'nit' not in col.lower():
            return col
    for col in df.columns:
        if 'nom' in col.lower() and 'nit' not in col.lower():
            return col
    return None

def _find_sede_name_column(df: pd.DataFrame) -> str:
    candidates = ['nom sede IPS', 'nom_sede_IPS', 'Nom sede', 'Nombre sede', 'nom sede', 'nom_sede',
                  'nom sede prestador', 'nom sede prestador', 'Nombre prestador', 'nom_sede_ips',
                  'Nom Sede IPS', 'nombre_sede', 'Nombre Sede', 'sede_nombre', 'Nom_sede_ips']
    for cand in candidates:
        for col in df.columns:
            if col.lower() == cand.lower():
                return col
    for col in df.columns:
        if 'sede' in col.lower() and ('nom' in col.lower() or 'nombre' in col.lower()):
            return col
    for col in df.columns:
        if 'nom' in col.lower() and 'nit' not in col.lower():
            return col
    return None

def _find_level_column(df: pd.DataFrame) -> str:
    candidates = ['num nivel atencion', 'num nivel', 'nivel', 'Nivel', 'num_nivel_atencion', 'nivel_atencion']
    for cand in candidates:
        for col in df.columns:
            if col.lower() == cand.lower():
                return col
    for col in df.columns:
        if 'nivel' in col.lower():
            return col
    return None

def _find_dept_mun_columns(df: pd.DataFrame):
    dept = next((c for c in df.columns if 'departamento' in c.lower()), None)
    mun = next((c for c in df.columns if 'municipio' in c.lower()), None)
    return dept, mun

def _find_service_column(df: pd.DataFrame) -> str:
    servicio_candidates = [
        'nom descripcion capacidad', 'nom_descripcion_capacidad', 'nom descripcion',
        'descripcion servicio', 'descripcion', 'Servicio', 'servicio', 'nom descripcion capacidad'
    ]
    for cand in servicio_candidates:
        for col in df.columns:
            if col.lower() == cand.lower():
                return col
    for col in df.columns:
        if 'descripcion' in col.lower() or 'servicio' in col.lower() or 'nom' in col.lower():
            return col
    for col in df.columns:
        if 'nit' not in col.lower() and 'codigo' not in col.lower():
            return col
    return None

def _build_name_lookup(df: pd.DataFrame, nit_col: str = 'nit_normalized') -> Dict[str, str]:
    if df is None or df.empty:
        return {}
    name_col = _find_name_column(df)
    lookup = {}
    if nit_col not in df.columns:
        return {}
    for _, row in df.drop_duplicates(subset=[nit_col]).iterrows():
        nit = row.get(nit_col)
        if pd.isna(nit) or nit is None:
            continue
        nit = str(nit)
        name = None
        if name_col and name_col in row.index:
            try:
                val = row.get(name_col)
                if pd.notna(val):
                    name = str(val)
            except Exception:
                name = None
        if not name:
            for alt in ['Nombre prestador', 'nom sede IPS', 'Nombre', 'Nombre_prestador', 'nom sede']:
                if alt in row.index and pd.notna(row.get(alt)):
                    name = str(row.get(alt))
                    break
        if not name:
            for alt in ['Código prestador', 'Código sede']:
                if alt in row.index and pd.notna(row.get(alt)):
                    name = str(row.get(alt))
                    break
        if not name:
            name = nit
        lookup[nit] = name
    return lookup

def compute_features(df: pd.DataFrame, nit: str, nit_col: str = 'nit_normalized') -> np.ndarray:
    subset = df[df[nit_col] == nit]
    if subset.empty:
        return np.array([0, 0, 0], dtype=np.float64)
    
    sede_col = next((c for c in subset.columns if 'código sede' in c.lower() or 'numero sede' in c.lower()), None)
    total_sedes = float(subset[sede_col].nunique()) if sede_col and pd.notna(subset[sede_col]).any() else 0.0
    
    serv_col = _find_service_column(subset)
    total_servicios = float(subset[serv_col].nunique()) if serv_col and pd.notna(subset[serv_col]).any() else 0.0
    
    cap_col = next((c for c in subset.columns if 'cantidad capacidad' in c.lower()), None)
    if cap_col and pd.notna(subset[cap_col]).any():
        try:
            total_capacidad = float(subset[cap_col].astype(float).sum())
        except (ValueError, TypeError):
            total_capacidad = 0.0
    else:
        total_capacidad = 0.0
    
    return np.array([total_sedes, total_servicios, total_capacidad], dtype=np.float64)

# ---------------- Simulation / processing (aligned with analysis_ips.py) ----------------
def simulate_for_ips_impl(ips_rows: pd.DataFrame, factor_operativo: float, nit_norm: str, consolidate_peers=False) -> pd.DataFrame:
    """
    Simulación de capacidad de atención, alineada con analysis_ips.py.
    Procesa datos por sede y servicio, calcula usuarios estimados usando estándares o escaladores de respaldo.
    """
    if ips_rows is None or ips_rows.empty:
        return pd.DataFrame()
    df = ips_rows.copy()
    # Build sede_id as codigo_sede|numero_sede
    codigo_sede_col = next((c for c in ['Código sede', 'Codigo sede', 'codigo_sede', 'Código_sede', 'Cod. sede', 'Codigo Sede', 'cod_sede_ips'] if c in df.columns), None)
    numero_sede_col = next((c for c in ['Número sede', 'Numero sede', 'numero_sede', 'num sede', 'numero_sede', 'nro sede', 'nro_sede'] if c in df.columns), None)
    nombre_sede_col = _find_sede_name_column(df)
    def build_sede_id(row):
        parts = []
        if codigo_sede_col and pd.notna(row.get(codigo_sede_col)):
            parts.append(str(row.get(codigo_sede_col)).strip())
        if numero_sede_col and pd.notna(row.get(numero_sede_col)):
            parts.append(str(row.get(numero_sede_col)).strip())
        if parts:
            return "|".join(parts)
        if codigo_sede_col and pd.notna(row.get(codigo_sede_col)):
            return str(row.get(codigo_sede_col)).strip()
        if nombre_sede_col and pd.notna(row.get(nombre_sede_col)):
            return str(row.get(nombre_sede_col)).strip()
        return f"{nit_norm}_unknown"
    df['sede_id'] = df.apply(build_sede_id, axis=1)
    # Verificar y limpiar columnas críticas
    if 'Descripción del servicio' not in df.columns:
        servicio_col = _find_service_column(df)
        if servicio_col:
            df = df.rename(columns={servicio_col: 'Descripción del servicio'})
        else:
            st.error(f"Datos insuficientes para {nit_norm}: no se encontró columna de servicio válida.")
            return pd.DataFrame()
    df['Descripción del servicio'] = df['Descripción del servicio'].astype(str).replace('', 'Sin servicio').fillna('Sin servicio')
    if 'num cantidad capacidad instalada' not in df.columns:
        st.warning(f"Columna 'num cantidad capacidad instalada' faltante para {nit_norm}. Usando conteo como fallback.")
        df['num cantidad capacidad instalada'] = 1
    # Build table of interest
    select_cols = ['sede_id', 'Descripción del servicio']
    for cand in ['Código sede', 'Codigo sede', 'Número sede', 'Numero sede', 'Nombre sede', 'nombre_sede', 'Departamento', 'Municipio', 'num nivel atencion']:
        if cand in df.columns and cand not in select_cols:
            select_cols.append(cand)
    tabla = df.loc[:, [c for c in select_cols if c in df.columns]].copy()
    tabla = tabla.drop_duplicates(subset=['sede_id', 'Descripción del servicio']).reset_index(drop=True)
    # Units map
    units_map = {}
    if 'num cantidad capacidad instalada' in df.columns:
        try:
            df['num cantidad capacidad instalada'] = pd.to_numeric(df['num cantidad capacidad instalada'], errors='coerce').fillna(0)
            # Limitar valores grandes antes de cualquier operación
            df['num cantidad capacidad instalada'] = df['num cantidad capacidad instalada'].clip(upper=10000)
            if not consolidate_peers:  # Desglose por sede
                units_series = df.groupby(['sede_id', 'Descripción del servicio'])['num cantidad capacidad instalada'].sum()
            else:  # Consolidación por servicio
                units_series = df.groupby('Descripción del servicio')['num cantidad capacidad instalada'].sum()
            units_map = {(str(k[0]), str(k[1])): min(int(v), 10000) for k, v in units_series.items() if pd.notna(v)}
        except Exception as e:
            st.warning(f"Error al crear units_map para {nit_norm}: {e}. Usando desglose por sede.")
            if not consolidate_peers:
                units_series = df.groupby(['sede_id', 'Descripción del servicio'])['num cantidad capacidad instalada'].sum()
                units_map = {(str(k[0]), str(k[1])): min(int(v), 10000) for k, v in units_series.items() if pd.notna(v)}
            else:
                units_map = {}
    counts_map = {}
    try:
        if not consolidate_peers:
            counts_series = df.groupby(['sede_id', 'Descripción del servicio']).size()
        else:
            counts_series = df.groupby('Descripción del servicio').size()
        counts_map = {(str(k[0]), str(k[1])): min(int(v), 10000) for k, v in counts_series.items()}
    except Exception as e:
        st.warning(f"Error al crear counts_map para {nit_norm}: {e}. Usando desglose por sede.")
        if not consolidate_peers:
            counts_series = df.groupby(['sede_id', 'Descripción del servicio']).size()
            counts_map = {(str(k[0]), str(k[1])): min(int(v), 10000) for k, v in counts_series.items()}
        else:
            counts_map = {}
    def get_qty(row):
        key = (str(row.get('sede_id', '')), str(row.get('Descripción del servicio', ''))) if not consolidate_peers else (str(row.get('Descripción del servicio', '')))
        qty = units_map.get(key, 0) if units_map.get(key, 0) > 0 else counts_map.get(key, 0)
        return min(qty, 10000)  # Límite adicional
    tabla['Cantidad del servicio'] = tabla.apply(get_qty, axis=1).astype(int)
    # Expected daily base using standards
    expected_daily_list = []
    matched_list = []
    debug_list = []
    for _, r in tabla.iterrows():
        svc_text = str(r.get('Descripción del servicio', ''))
        std = find_standard_for_service(svc_text)
        key = (str(r.get('sede_id', '')), svc_text) if not consolidate_peers else (svc_text,)
        units = units_map.get(key, 0)
        if units == 0:
            units = int(r.get('Cantidad del servicio', 0))
        if std is not None and units > 0:
            expected_daily = round(units * float(std['daily_per_unit']), 1)
            expected_daily_list.append(min(expected_daily, 20000))  # Límite de 20,000
            matched_list.append(std['matched_key'])
            debug_list.append(f"Matched: {std['matched_key']}, Units: {units}, Daily: {expected_daily}")
        else:
            base_count = int(r.get('Cantidad del servicio', 0))
            if base_count == 0:
                base_count = 1
            s_lower = svc_text.lower()
            if any(k in s_lower for k in ['camas', 'camillas', 'cuna', 'incubadora']):
                scale = 0.18
            elif any(k in s_lower for k in ['sala', 'quirófano', 'quirofano']):
                scale = 5.0
            else:
                scale = 10.0
            expected_daily = round(base_count * scale, 1)
            expected_daily_list.append(min(expected_daily, 20000))
            matched_list.append(None)
            debug_list.append(f"Fallback scale={scale}, Base: {base_count}, Daily: {expected_daily}")
    tabla['_expected_daily_base'] = expected_daily_list
    tabla['_matched_standard_key'] = matched_list
    tabla['_debug'] = debug_list
    # Simulate per row
    daily_list = []
    weekly_list = []
    monthly_list = []
    for _, row in tabla.iterrows():
        svc = str(row.get('Descripción del servicio', ''))
        expected_base = row.get('_expected_daily_base', None)
        seed = hash_seed(nit_norm, str(row.get('sede_id', '')), svc)
        rng = np.random.default_rng(seed)
        noise = rng.normal(loc=1.0, scale=0.05)
        utilization = max(0.1, float(factor_operativo) * noise)
        if expected_base is not None:
            daily_est = max(1, int(round(float(expected_base) * utilization)))
        else:
            base_count = int(row.get('Cantidad del servicio', 0))
            if base_count == 0:
                base_count = 1
            if base_count < 5:
                scale = 5
            else:
                scale = min(20, max(5, int(base_count / 2)))
            daily_est = max(1, int(round(base_count * scale * utilization)))
        daily_est = min(daily_est, 20000)  # Límite final de usuarios diarios
        weekly_est = daily_est * 7
        monthly_est = daily_est * 30
        daily_list.append(daily_est)
        weekly_list.append(weekly_est)
        monthly_list.append(monthly_est)
    tabla['Usuarios diarios estimados'] = daily_list
    tabla['Usuarios semanales estimados'] = weekly_list
    tabla['Usuarios mensuales estimados'] = monthly_list
    # Normalize column names
    if 'num nivel atencion' in tabla.columns:
        tabla = tabla.rename(columns={'num nivel atencion': 'Nivel'})
    if nombre_sede_col and nombre_sede_col in tabla.columns:
        tabla = tabla.rename(columns={nombre_sede_col: 'Nombre sede'})
    if codigo_sede_col and codigo_sede_col in tabla.columns:
        tabla = tabla.rename(columns={codigo_sede_col: 'Código sede'})
    if numero_sede_col and numero_sede_col in tabla.columns:
        tabla = tabla.rename(columns={numero_sede_col: 'Número sede'})
    # Build _label
    def make_label(r):
        code = str(r.get('Código sede', '')) if 'Código sede' in r.index else ''
        num = str(r.get('Número sede', '')) if 'Número sede' in r.index else ''
        name = str(r.get('Nombre sede', '')) if 'Nombre sede' in r.index else ''
        if code and num:
            return f"{code}|{num} - {name}" if name else f"{code}|{num}"
        if code:
            return f"{code} - {name}" if name else code
        if name:
            return name
        return str(r.get('sede_id', ''))
    tabla['_label'] = tabla.apply(make_label, axis=1)
    preferred = [
        'sede_id', 'Código sede', 'Número sede', 'Departamento', 'Municipio', 'Nivel', 'Nombre sede', '_label',
        'Descripción del servicio', 'Cantidad del servicio', '_expected_daily_base', '_matched_standard_key',
        '_debug', 'Usuarios diarios estimados', 'Usuarios semanales estimados', 'Usuarios mensuales estimados'
    ]
    sim_display = tabla.loc[:, [c for c in preferred if c in tabla.columns] + [c for c in tabla.columns if c not in preferred]]
    return sim_display

def compute_summary_metrics(sim_df: pd.DataFrame) -> Dict[str, int]:
    """
    Calcula métricas resumidas: total de sedes, servicios, usuarios diarios y mensuales.
    """
    if sim_df is None or sim_df.empty:
        return {'total_sedes': 0, 'total_servicios': 0, 'usuarios_diarios': 0, 'usuarios_mensuales': 0}
    total_sedes = int(sim_df['sede_id'].nunique()) if 'sede_id' in sim_df.columns else 0
    total_servicios = int(sim_df['Descripción del servicio'].nunique()) if 'Descripción del servicio' in sim_df.columns else 0
    usuarios_diarios = int(sim_df['Usuarios diarios estimados'].sum()) if 'Usuarios diarios estimados' in sim_df.columns else 0
    usuarios_mensuales = int(sim_df['Usuarios mensuales estimados'].sum()) if 'Usuarios mensuales estimados' in sim_df.columns else 0
    return {'total_sedes': total_sedes, 'total_servicios': total_servicios, 'usuarios_diarios': usuarios_diarios, 'usuarios_mensuales': usuarios_mensuales}

# ---------------- Page entrypoint ----------------
def run(filtered_df: pd.DataFrame, nits_display: List[str], df_all: pd.DataFrame, filters: dict):
    """
    Punto de entrada de la página de comparaciones de IPS.
    Permite comparar una IPS de referencia con peers seleccionados.
    """
    st.title("Comparaciones de IPS - Peers por Nivel de Complejidad (Selección Robusta)")
    factor_default = float(filters.get("factor_operativo", 1.0))
    factor_operativo = st.sidebar.slider("Factor operativo (Comparaciones)", 0.5, 1.5, factor_default, 0.01, key='cmp_factor')
    # Entrada manual del NIT de referencia
    nit_input_raw = st.text_input("NIT de referencia (sin separadores ni dígito verificador)", value="")
    nit_input = _clean_nit_str(nit_input_raw)
    if not nit_input:
        st.info("Introduce el NIT de referencia (sin comas ni dígito verificador) para iniciar la comparación.")
        return
    # Asegurarse de que df_all tenga nit_normalized
    df = df_all.copy() if df_all is not None else pd.DataFrame()
    if 'nit_normalized' not in df.columns:
        if 'nit IPS' in df.columns:
            try:
                df['nit_normalized'] = df['nit IPS'].astype(str).apply(_clean_nit_str)
            except Exception:
                df['nit_normalized'] = df['nit IPS'].astype(str).str.replace(r'\D', '', regex=True)
        else:
            df['nit_normalized'] = pd.NA
    # Buscar filas de la referencia
    matches_ref = df[df['nit_normalized'] == nit_input] if not df.empty else pd.DataFrame()
    if matches_ref.empty:
        st.error(f"No se encontraron filas para el NIT de referencia {nit_input_raw} (normalizado: {nit_input}).")
        return
    # Construir ips_ref
    idxs_ref = matches_ref.index.unique().tolist()
    ips_ref = df.loc[idxs_ref].reset_index(drop=True)
    # Mostrar tabla de sedes únicas
    if 'Código sede' in ips_ref.columns and 'Número sede' in ips_ref.columns:
        ips_ref['Sede ID'] = ips_ref['Código sede'].astype(str) + '|' + ips_ref['Número sede'].astype(str)
    else:
        ips_ref['Sede ID'] = ips_ref.index.astype(str)
    sedes_df = ips_ref[['Sede ID', 'nom sede IPS', 'Departamento', 'Municipio', 'num nivel atencion']].drop_duplicates(subset=['Sede ID'])
    sedes_df.columns = ['Sede ID', 'Nombre de Sede', 'Departamento', 'Municipio', 'Nivel']
    st.subheader("Sedes disponibles para el NIT de referencia")
    st.dataframe(sedes_df, use_container_width=True)
    # Menú desplegable para seleccionar sede con nombres
    sedes_options = ['Todas'] + [f"{row['Nombre de Sede']} (Sede ID: {row['Sede ID']})" for _, row in sedes_df.iterrows()]
    sede_id_mapping = {f"{row['Nombre de Sede']} (Sede ID: {row['Sede ID']}": row['Sede ID'] for _, row in sedes_df.iterrows()}
    selected_sede_display = st.selectbox("Seleccionar sede de la referencia (o 'Todas' para consolidar)", options=sedes_options, index=0)
    selected_sede_id = sede_id_mapping.get(selected_sede_display) if selected_sede_display in sede_id_mapping else None
    if selected_sede_display != 'Todas' and selected_sede_id:
        ips_ref = ips_ref[ips_ref['Sede ID'] == selected_sede_id]
        if ips_ref.empty:
            st.warning(f"No se encontraron datos para la sede {selected_sede_display}.")
    # Build name lookup
    name_lookup = _build_name_lookup(df, nit_col='nit_normalized')
    ref_name = name_lookup.get(nit_input, nit_input)
    # Determinar nivel / geografía de referencia
    nivel_col = _find_level_column(ips_ref)
    ref_nivel_value = None
    if nivel_col and not ips_ref[nivel_col].dropna().empty:
        ref_nivel_value = ips_ref[nivel_col].dropna().astype(str).mode().iloc[0]
    if not ref_nivel_value and nivel_col:
        st.warning(f"No se pudo determinar un nivel único para la referencia {nit_input}. Usando todos los niveles disponibles.")
    dept_col, mun_col = _find_dept_mun_columns(ips_ref)
    ref_dept = ips_ref[dept_col].dropna().astype(str).mode().iloc[0] if dept_col and not ips_ref[dept_col].dropna().empty else None
    ref_mun = ips_ref[mun_col].dropna().astype(str).mode().iloc[0] if mun_col and not ips_ref[mun_col].dropna().empty else None
    st.markdown("Filtra peers por nivel y (opcional) por ubicación para obtener IPS similares.")
    candidates_df = df.copy()
    if ref_nivel_value and nivel_col in candidates_df.columns:
        candidates_df = candidates_df[candidates_df[nivel_col].astype(str) == str(ref_nivel_value)]
    else:
        st.warning("No se aplicó filtrado por nivel debido a la ausencia o inconsistencia del nivel de referencia.")
    filter_by_geo = st.checkbox("Limitar peers al mismo Departamento y Municipio que la referencia", value=False)
    if filter_by_geo and ref_dept and dept_col and ref_dept in candidates_df[dept_col].astype(str).values:
        candidates_df = candidates_df[candidates_df[dept_col].astype(str) == str(ref_dept)]
    if filter_by_geo and ref_mun and mun_col and ref_mun in candidates_df[mun_col].astype(str).values:
        candidates_df = candidates_df[candidates_df[mun_col].astype(str) == str(ref_mun)]
    # Obtener lista de peers (NITs) y verificar niveles
    peer_nits = []
    try:
        if explode_nits_regex is not None:
            exploded_cand = explode_nits_regex(candidates_df, 'nit IPS')
            if exploded_cand is not None and not exploded_cand.empty and 'nit_token' in exploded_cand.columns:
                peer_nits = sorted(set(re.sub(r'\D', '', str(x)) for x in exploded_cand['nit_token'].dropna().astype(str).tolist()))
    except Exception as e:
        st.warning(f"Error al explotar NITs: {e}. Usando nit_normalized.")
        exploded_cand = None
    if not peer_nits and 'nit_normalized' in candidates_df.columns:
        peer_nits = sorted(list(set(candidates_df['nit_normalized'].dropna().astype(str).tolist())))
    # Verificar que los peers tengan el nivel correcto
    if ref_nivel_value and nivel_col in candidates_df.columns:
        peer_nits = [p for p in peer_nits if p != nit_input and p in candidates_df[candidates_df[nivel_col].astype(str) == str(ref_nivel_value)]['nit_normalized'].astype(str).values]
    else:
        peer_nits = [p for p in peer_nits if p != nit_input]
    if not peer_nits:
        st.warning("No se encontraron peers con los filtros actuales. Ajusta Nivel/geografía o verifica los datos.")
    # Computar features de referencia
    ref_features = compute_features(df, nit_input)
    # Computar similitudes y ordenar peers
    similarities = []
    for p in peer_nits:
        peer_features = compute_features(df, p)
        if np.all(peer_features == 0):
            continue
        distance = np.linalg.norm(ref_features - peer_features)
        similarities.append((p, distance))
    if similarities:
        similarities.sort(key=lambda x: x[1])
        peer_nits_sorted = [p for p, d in similarities]
    else:
        peer_nits_sorted = peer_nits
    st.markdown("Selecciona peers (máx 10; por defecto se seleccionan hasta 5 más similares por similitud en sedes, servicios y capacidad).")
    default_peers = peer_nits_sorted[:5]
    selected_peers = st.multiselect("Peers similares (NITs, ordenados por similitud)", options=peer_nits_sorted, default=default_peers)
    # Entrada manual para NITs de peers
    manual_nits_raw = st.text_input("NITs adicionales de peers (separados por comas o espacios, opcional)", value="")
    manual_nits = []
    if manual_nits_raw:
        manual_nits = [_clean_nit_str(nit) for nit in re.split(r'[,\s]+', manual_nits_raw.strip()) if _clean_nit_str(nit)]
        valid_manual_nits = [
            nit for nit in manual_nits
            if nit in df['nit_normalized'].astype(str).values and nit != nit_input and (
                not ref_nivel_value or
                nit in candidates_df[candidates_df[nivel_col].astype(str) == str(ref_nivel_value)]['nit_normalized'].astype(str).values
            )
        ]
        invalid_nits = [nit for nit in manual_nits if nit not in df['nit_normalized'].astype(str).values or (ref_nivel_value and nit not in candidates_df[candidates_df[nivel_col].astype(str) == str(ref_nivel_value)]['nit_normalized'].astype(str).values)]
        if invalid_nits:
            st.warning(f"Los siguientes NITs ingresados no se encontraron o no coinciden con el nivel de referencia: {', '.join(invalid_nits)}")
        manual_nits = valid_manual_nits
    selected_peers = list(set(selected_peers + manual_nits) - {nit_input})
    if len(selected_peers) > 10:
        st.warning("Has seleccionado más de 10 peers; se tomarán sólo los primeros 10 seleccionados.")
        selected_peers = selected_peers[:10]
    if not selected_peers:
        st.warning("Selecciona al menos un peer para comparar (o ingresa NITs manualmente o ajusta filtros).")
        return
    # Nueva opción para consolidar peers
    consolidate_peers = st.checkbox("Consolidar capacidad de peers (sumar todas las sedes por NIT)", value=False)
    # Generar simulaciones
    st.markdown("Generando simulaciones (cacheadas por NIT + factor).")
    try:
        sim_ref = simulate_for_ips_impl(ips_ref, factor_operativo, nit_input, consolidate_peers=False)
        sim_peers: Dict[str, pd.DataFrame] = {}
        exploded_all_full = df
        for peer_nit in selected_peers:
            nit_norm_peer = peer_nit
            matches_peer = exploded_all_full[exploded_all_full['nit_normalized'] == nit_norm_peer] if not exploded_all_full.empty else pd.DataFrame()
            if matches_peer.empty:
                sim_peers[peer_nit] = pd.DataFrame()
                continue
            idxs_peer = matches_peer.index.unique().tolist()
            ips_peer_rows = df.loc[idxs_peer].reset_index(drop=True)
            peer_level = ips_peer_rows[nivel_col].dropna().mode().iloc[0] if nivel_col in ips_peer_rows.columns and not ips_peer_rows[nivel_col].dropna().empty else None
            if ref_nivel_value and peer_level and str(peer_level) != str(ref_nivel_value):
                st.warning(f"Peer {peer_nit} (Nivel {peer_level}) excluido por no coincidir con el nivel de referencia {ref_nivel_value}")
                continue
            servicio_col = _find_service_column(ips_peer_rows)
            if not servicio_col:
                st.warning(f"No se encontró columna de servicio para el peer {peer_nit}. Usando índice como servicio.")
                ips_peer_rows['Descripción del servicio'] = ips_peer_rows.index.astype(str)
            elif servicio_col != 'Descripción del servicio':
                ips_peer_rows = ips_peer_rows.rename(columns={servicio_col: 'Descripción del servicio'})
            ips_peer_rows = ips_peer_rows.dropna(subset=['Descripción del servicio'])
            if not consolidate_peers:
                sim_peer = simulate_for_ips_impl(ips_peer_rows, factor_operativo, nit_norm_peer, consolidate_peers=False)
            else:
                if 'num cantidad capacidad instalada' in ips_peer_rows.columns and 'Descripción del servicio' in ips_peer_rows.columns:
                    try:
                        ips_peer_rows['num cantidad capacidad instalada'] = ips_peer_rows['num cantidad capacidad instalada'].clip(upper=10000)
                        consolidated = ips_peer_rows.groupby('Descripción del servicio', as_index=False)['num cantidad capacidad instalada'].sum()
                        consolidated['sede_id'] = f"{nit_norm}_consolidado"
                        sim_peer = simulate_for_ips_impl(consolidated, factor_operativo, nit_norm_peer, consolidate_peers=True)
                    except Exception as e:
                        st.warning(f"Error al consolidar peer {peer_nit}: {e}. Usando desglose por sede.")
                        sim_peer = simulate_for_ips_impl(ips_peer_rows, factor_operativo, nit_norm_peer, consolidate_peers=False)
                else:
                    st.warning(f"Datos insuficientes para consolidar {peer_nit}. Usando desglose por sede.")
                    sim_peer = simulate_for_ips_impl(ips_peer_rows, factor_operativo, nit_norm_peer, consolidate_peers=False)
            sim_peers[peer_nit] = sim_peer
    except Exception as e:
        st.error(f"Error generando simulaciones: {e}")
        st.exception(traceback.format_exc())
        return
    # Build table with all IPS analyzed
    analyzed_nits = [nit_input] + selected_peers
    rows = []
    sede_name_col = _find_sede_name_column(df)
    level_col = _find_level_column(df)
    dept_col_master, mun_col_master = _find_dept_mun_columns(df)
    for n in analyzed_nits:
        subset = df[df['nit_normalized'] == n]
        if subset.empty:
            continue
        r = subset.iloc[0].to_dict()
        name_sede = None
        if sede_name_col and sede_name_col in r and pd.notna(r.get(sede_name_col)):
            name_sede = r.get(sede_name_col)
        else:
            for alt in ['Nombre prestador', 'Nombre', 'nom sede IPS', 'nom sede', 'nombre_prestador']:
                if alt in r and pd.notna(r.get(alt)):
                    name_sede = r.get(alt)
                    break
        if not name_sede:
            name_sede = name_lookup.get(n, n)
        nivel_val = r.get(level_col, '') if level_col and level_col in r else ''
        dept_val = r.get(dept_col_master, '') if dept_col_master and dept_col_master in r else ''
        mun_val = r.get(mun_col_master, '') if mun_col_master and mun_col_master in r else ''
        rows.append({
            "NIT": n,
            "Nombre sede": name_sede,
            "Nivel": nivel_val,
            "Departamento": dept_val,
            "Municipio": mun_val
        })
    if rows:
        st.subheader("IPS analizadas (Referencia + Peers seleccionados)")
        analyzed_df = pd.DataFrame(rows)
        analyzed_df = analyzed_df.set_index('NIT').reindex(analyzed_nits).reset_index()
        st.dataframe(analyzed_df, use_container_width=True)
    # Calcular métricas
    ref_metrics = compute_summary_metrics(sim_ref)
    peers_metrics = {p: compute_summary_metrics(sim_peers.get(p, pd.DataFrame())) for p in selected_peers}
    display_name = {n: name_lookup.get(n, n) for n in analyzed_nits}
    st.subheader("Tabla comparativa de métricas clave")
    metric_rows = []
    metric_names = [
        ('total_sedes', 'Total sedes'),
        ('total_servicios', 'Servicios únicos'),
        ('usuarios_diarios', 'Usuarios diarios (total)'),
        ('usuarios_mensuales', 'Usuarios mensuales (total)')
    ]
    for key, label in metric_names:
        ref_val = ref_metrics.get(key, 0)
        row = {'Métrica': label, 'Referencia': ref_val}
        for p in selected_peers:
            peer_val = peers_metrics.get(p, {}).get(key, 0)
            pct_diff = ((peer_val - ref_val) / ref_val * 100.0) if ref_val and ref_val != 0 else None
            col_name_val = f"{display_name.get(p,p)} ({p})"
            col_name_pct = f"{display_name.get(p,p)} ({p}) % diff"
            row[col_name_val] = peer_val
            row[col_name_pct] = f"{pct_diff:.1f}%" if pct_diff is not None else "N/A"
        metric_rows.append(row)
    comp_df = pd.DataFrame(metric_rows)
    for col in comp_df.columns:
        if col != 'Métrica':
            try:
                comp_df[col] = comp_df[col].apply(lambda x: format_number(int(x)) if (isinstance(x, (int, float)) and not pd.isna(x)) else x)
            except Exception:
                pass
    st.dataframe(comp_df, use_container_width=True)
    st.subheader("Top servicios: Usuarios diarios por servicio (Referencia vs Peers)")
    def agg_by_service(sim_df: pd.DataFrame) -> pd.DataFrame:
        if sim_df is None or sim_df.empty:
            return pd.DataFrame(columns=['Descripción del servicio', 'Usuarios diarios'])
        df2 = sim_df.groupby('Descripción del servicio', dropna=False)['Usuarios diarios estimados'].sum().reset_index()
        df2 = df2.rename(columns={'Usuarios diarios estimados': 'Usuarios diarios'}).sort_values('Usuarios diarios', ascending=False)
        return df2
    ref_by_serv = agg_by_service(sim_ref)
    peers_by_serv = {p: agg_by_service(sim_peers.get(p, pd.DataFrame())) for p in selected_peers}
    svc_candidates = list(ref_by_serv.head(5)['Descripción del servicio'].astype(str).tolist()) if not ref_by_serv.empty else []
    for p, dfp in peers_by_serv.items():
        if not dfp.empty:
            svc_candidates += dfp.head(5)['Descripción del servicio'].astype(str).tolist()
    svc_candidates = list(pd.Index(svc_candidates).unique())[:10]
    plot_rows = []
    for svc in svc_candidates:
        ref_val = int(ref_by_serv.loc[ref_by_serv['Descripción del servicio'].astype(str) == str(svc), 'Usuarios diarios'].sum()) if not ref_by_serv.empty else 0
        plot_rows.append({'Servicio': svc, 'IPS': display_name.get(nit_input, nit_input), 'NIT': nit_input, 'Usuarios Diarios': ref_val})
        for p in selected_peers:
            pf = peers_by_serv.get(p, pd.DataFrame())
            peer_val = int(pf.loc[pf['Descripción del servicio'].astype(str) == str(svc), 'Usuarios diarios'].sum()) if not pf.empty else 0
            plot_rows.append({'Servicio': svc, 'IPS': display_name.get(p, p), 'NIT': p, 'Usuarios Diarios': peer_val})
    plot_df = pd.DataFrame(plot_rows)
    plot_df['Usuarios Diarios'] = plot_df['Usuarios Diarios'].astype(int)
    if plot_df.empty:
        st.info("No hay datos de servicios para graficar.")
    else:
        svc_options = ['Todos'] + svc_candidates
        selected_service = st.selectbox("Seleccionar servicio para visualizar", options=svc_options, index=0)
        if selected_service != 'Todos':
            plot_df_filtered = plot_df[plot_df['Servicio'] == selected_service]
            graph_title = f"Comparación IPS con {ref_name} - {selected_service}"
        else:
            plot_df_filtered = plot_df
            graph_title = f"Comparación IPS con {ref_name}"
        plot_df_filtered['Servicio'] = pd.Categorical(plot_df_filtered['Servicio'], categories=svc_candidates, ordered=True)
        fig = px.bar(plot_df_filtered, x='Servicio', y='Usuarios Diarios', color='IPS', barmode='group',
                     title=graph_title, hover_data=['NIT'])
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("*Fuente: REPS*")
        st.markdown("**Datos de Top Servicios (Referencia vs Peers)**")
        st.dataframe(plot_df_filtered[['Servicio', 'IPS', 'NIT', 'Usuarios Diarios']], use_container_width=True)
    st.subheader("KPIs globales")
    kcol1, kcol2, kcol3 = st.columns(3)
    kcol1.metric("Usuarios diarios (Referencia)", format_number(ref_metrics.get('usuarios_diarios', 0)))
    if selected_peers:
        peer_daily_vals = [peers_metrics[p]['usuarios_diarios'] for p in selected_peers if peers_metrics.get(p)]
        avg_peers_daily = int(round(float(np.mean(peer_daily_vals)))) if peer_daily_vals else 0
        kcol2.metric(f"Usuarios diarios (Promedio Peers, n={len(selected_peers)})", format_number(avg_peers_daily))
    else:
        kcol2.metric("Usuarios diarios (Promedio Peers)", "N/A")
    kcol3.metric("Sedes (Referencia)", format_number(ref_metrics.get('total_sedes', 0)))
    st.subheader("Exportar resultados")
    if st.button("Exportar a Excel (Comparación)"):
        try:
            sheets = {}
            sheets["Resumen_Comparativo"] = comp_df.copy()
            sheets["Simulacion_Ref"] = sim_ref.copy()
            for p in selected_peers:
                sheets[f"Simulacion_Peer_{p}"] = sim_peers.get(p, pd.DataFrame()).copy()
            if tables_comp is not None:
                tables_comp.download_excel(sheets, filename=f"comparacion_ips_{nit_input}.xlsx")
                st.success("Excel preparado para descarga.")
            else:
                st.warning("Componente de descarga no disponible (tables_comp).")
        except Exception as e:
            st.error(f"Error exportando Excel: {e}\n{traceback.format_exc()}")
    with st.expander("Detalle: Simulación Referencia (mostrar)"):
        st.dataframe(sim_ref, use_container_width=True)
    for p in selected_peers:
        with st.expander(f"Detalle: Simulación Peer {display_name.get(p, p)} ({p})"):
            st.dataframe(sim_peers.get(p, pd.DataFrame()), use_container_width=True)
    st.markdown("Fin de la página Comparaciones de IPS.")
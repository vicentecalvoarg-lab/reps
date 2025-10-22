"""
Analysis page implementing the simulator (wrapped with debug/exception reporting).

Interface:
    run(filters: dict, df_filtered: pd.DataFrame, df_all: pd.DataFrame)

This page:
 - muestra la radiografía y simulación por NIT (como antes)
 - añade al final la sección "Giros 2025 vs Capacidad mensual" que consulta
   el parquet de Giro Directo (ruta configurable por GIRO_PARQUET) y muestra:
     * tabla mes a mes (Ene-Dic 2025) con Giro (millones) y Capacidad mensual
     * gráfico con eje principal: COP por atención (barras)
Modificado: selección de servicios incluye "TODAS" y viene por defecto.
Se añadió al final un KPI destacado (rectángulo) que muestra el promedio
acumulado YTD del Giro/Capacidad (COP por atención).
"""
from pathlib import Path
import os
import traceback
from datetime import date
from typing import Optional

import streamlit as st
import pandas as pd
import numpy as np

# plotting / db
import plotly.express as px
import plotly.graph_objects as go
import duckdb

# local app imports (assumes package layout app.pagina etc)
from app.components import tables as tables_comp
from app.data import explode_nits_regex
from app.utils import normalize_nit, hash_seed, format_number
from app.standards import find_standard_for_service

LOG_DIR = Path("C:/REPS/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "analysis_ips_error.log"

def _log_and_show(tb_text: str):
    st.error("Se produjo una excepción en la página 'Análisis IPS'. Ver detalles abajo.")
    st.exception(tb_text)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(tb_text)
            f.write("\n\n")
    except Exception:
        pass

def get_giro_parquet_path() -> str:
    p = os.environ.get("GIRO_PARQUET")
    if p:
        return p
    return r"c:/evaluagiro/BD/Giro.parquet"

def _find_nit_col_in_parquet(parquet_path: str, con: duckdb.DuckDBPyConnection) -> Optional[str]:
    """
    Try a list of candidate column names until one works in a quick query.
    Returns the column name or None.
    """
    candidates = [
        "nit", "NIT", "Nit", "NIT IPS", "nit IPS", "NIT_Prestador", "nit_prestador",
        "nit_ips", "NIT_PRESTADOR", "Nit Prestador", "Nit_prestador", "nit_prestador"
    ]
    for c in candidates:
        try:
            q = f"SELECT 1 FROM '{parquet_path}' WHERE {quote_col(c)} IS NOT NULL LIMIT 1"
            con.execute(q).fetchdf()
            return c
        except Exception:
            continue
    return None

def quote_col(col: str) -> str:
    return f'"{col}"'

def quote_val(val: str) -> str:
    if val is None:
        return "NULL"
    s = str(val).replace("'", "''")
    return f"'{s}'"

def format_int_commas(x) -> str:
    try:
        if pd.isna(x):
            return ""
        return f"{int(round(float(x))):,}"
    except Exception:
        return str(x)

def run(filters: dict, df_filtered: pd.DataFrame, df_all: pd.DataFrame):
    st.write("DEBUG: entered analysis_ips")
    try:
        st.header("Análisis IPS — Simulación (centralizado)")

        # Use df_filtered for the analysis scope
        df = df_filtered.copy()

        st.write(f"Filas disponibles para este análisis: {len(df):,}")

        # Prepare NIT list for selection (explode if needed)
        exploded = explode_nits_regex(df, 'nit IPS')
        nits = sorted(exploded['nit_token'].dropna().unique()) if not exploded.empty else []
        nit_select = st.selectbox("Selecciona NIT (o deja vacío)", [""] + nits, index=0)
        nit_input = st.text_input("O ingresa NIT manualmente (sin dígito verificador)")
        nit_to_search = nit_input.strip() if nit_input.strip() else (nit_select.strip() if nit_select else "")
        if not nit_to_search:
            st.info("Selecciona o ingresa un NIT para ver la radiografía y simulación.")
            return

        nit_norm = normalize_nit(nit_to_search)

        # Find matches across the full dataset (df_all) to be consistent with previous behavior
        exploded_all = explode_nits_regex(df_all, 'nit IPS')
        matches = exploded_all[exploded_all['nit_normalized'] == nit_norm] if not exploded_all.empty else pd.DataFrame()
        if matches.empty:
            st.error(f"No se encontró el NIT {nit_to_search}")
            return
        idxs = matches['_orig_index'].unique().tolist()
        ips_rows = df_all.loc[idxs].reset_index(drop=True)

        # Build sede_id as codigo_sede + '|' + numero_sede when available
        codigo_sede_col = next((c for c in ['Código sede','Codigo sede','codigo sede','codigo_sede','Cod. sede','Codigo Sede'] if c in ips_rows.columns), None)
        numero_sede_col = next((c for c in ['Número sede','Numero sede','numero sede','num sede','numero_sede','nro sede'] if c in ips_rows.columns), None)
        nombre_sede_col = next((c for c in ['nom sede IPS','nom sede ips','Nom sede IPS','nom_sede_ips','Nombre sede','nombre_sede','Nombre de la sede'] if c in ips_rows.columns), None)

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
            return "sede_unknown"

        ips_rows = ips_rows.copy()
        ips_rows['sede_id'] = ips_rows.apply(build_sede_id, axis=1)

        # Build unique sedes table
        cols_for_sede = []
        if codigo_sede_col: cols_for_sede.append(codigo_sede_col)
        if numero_sede_col: cols_for_sede.append(numero_sede_col)
        if nombre_sede_col: cols_for_sede.append(nombre_sede_col)
        if 'Departamento' in ips_rows.columns: cols_for_sede.append('Departamento')
        if 'Municipio' in ips_rows.columns: cols_for_sede.append('Municipio')
        if 'num nivel atencion' in ips_rows.columns: cols_for_sede.append('num nivel atencion')
        sede_unicas = ips_rows[cols_for_sede + ['sede_id']].drop_duplicates(subset=['sede_id']).reset_index(drop=True)

        # Normalise column names for display
        if 'num nivel atencion' in sede_unicas.columns:
            sede_unicas = sede_unicas.rename(columns={'num nivel atencion': 'Nivel'})
        if nombre_sede_col and nombre_sede_col in sede_unicas.columns:
            sede_unicas = sede_unicas.rename(columns={nombre_sede_col: 'Nombre sede'})
        if codigo_sede_col and codigo_sede_col in sede_unicas.columns:
            sede_unicas = sede_unicas.rename(columns={codigo_sede_col: 'codigo_sede'})
        if numero_sede_col and numero_sede_col in sede_unicas.columns:
            sede_unicas = sede_unicas.rename(columns={numero_sede_col: 'numero_sede'})

        st.subheader("Sedes únicas del NIT")
        if sede_unicas.empty:
            st.info("No se encontraron sedes.")
        else:
            cols_show = [c for c in ['codigo_sede','numero_sede','Nombre sede','Departamento','Municipio','Nivel','sede_id'] if c in sede_unicas.columns]
            st.dataframe(sede_unicas[cols_show], use_container_width=True)

            # Summary by complexity level (Cantidad IPS counted as unique codigo+numero)
            nivel_col = 'Nivel' if 'Nivel' in sede_unicas.columns else None
            servicio_col = next((c for c in ['nom descripcion capacidad','nom_descripcion_capacidad','nom descripcion','descripcion servicio','descripcion','Servicio','servicio'] if c in ips_rows.columns), None)

            if nivel_col:
                niveles = []
                levels_values = sorted(sede_unicas[nivel_col].dropna().unique().tolist())
                for lvl in levels_values:
                    mask_lvl = sede_unicas[nivel_col] == lvl
                    # count unique codigo_sede+numero_sede combos
                    if 'codigo_sede' in sede_unicas.columns and 'numero_sede' in sede_unicas.columns:
                        temp = sede_unicas.loc[mask_lvl, ['codigo_sede','numero_sede']].fillna("").astype(str)
                        combos = temp.apply(lambda x: (x.iloc[0].strip() + "|" + x.iloc[1].strip()).strip("|"), axis=1)
                        combos = combos[combos != ""]
                        qty_ips = int(combos.nunique())
                    else:
                        qty_ips = int(sede_unicas.loc[mask_lvl, 'sede_id'].nunique())
                    # services in ips_rows for that level
                    if servicio_col and servicio_col in ips_rows.columns:
                        if 'num nivel atencion' in ips_rows.columns:
                            qty_services = int(ips_rows.loc[ips_rows['num nivel atencion'] == lvl, servicio_col].dropna().astype(str).nunique())
                        else:
                            qty_services = int(ips_rows.loc[ips_rows['sede_id'].isin(sede_unicas.loc[mask_lvl,'sede_id']), servicio_col].dropna().astype(str).nunique())
                    else:
                        qty_services = 0
                    niveles.append({'Nivel de complejidad': lvl, 'Cantidad de IPS': qty_ips, 'Cantidad de servicios ofrecidos': qty_services})
                resumen_nivel_df = pd.DataFrame(niveles)
                st.subheader("Resumen por Nivel de complejidad")
                st.dataframe(resumen_nivel_df, use_container_width=True)
            else:
                st.info("No hay columna de Nivel para hacer resumen por nivel.")

        # --------------------
        # Sedes por Servicio
        # --------------------
        st.subheader("Sedes por Servicio")
        servicio_used = servicio_col
        if servicio_used:
            servicios_counts = ips_rows.groupby(servicio_used).size().reset_index(name='Cantidad')
            servicios_counts = servicios_counts.rename(columns={servicio_used:'Descripción del servicio'}).sort_values('Cantidad', ascending=False).reset_index(drop=True)
            st.dataframe(servicios_counts, use_container_width=True)
            servicio_values = servicios_counts['Descripción del servicio'].dropna().astype(str).tolist()
        else:
            st.info("No hay columna de servicio.")
            servicio_values = []

        # --- Selection de servicios: incluir "TODAS" por defecto ---
        service_options = ["TODAS"] + sorted(set(servicio_values))
        servicio_seleccionado = st.multiselect(
            "Selecciona servicio(s):",
            options=service_options,
            default=["TODAS"],
            help="Elija 'TODAS' para incluir todos los servicios"
        )

        # Normalizar selección: si se eligió "TODAS" usamos la lista completa de servicios
        if servicio_seleccionado is None:
            servicio_seleccionado = []

        if "TODAS" in servicio_seleccionado:
            servicio_selected_list = servicio_values  # todas las descripciones
        else:
            servicio_selected_list = servicio_seleccionado

        # Build tabla_sedes_servicio (same logic as before)
        tabla_sedes_servicio = pd.DataFrame()
        if servicio_selected_list and servicio_used:
            mask = pd.Series(False, index=ips_rows.index)
            for sv in servicio_selected_list:
                mask = mask | ips_rows[servicio_used].astype(str).str.contains(sv, case=False, na=False)
            ips_servicio = ips_rows[mask].copy().reset_index(drop=True)

            select_cols = ['sede_id']
            if codigo_sede_col and codigo_sede_col in ips_servicio.columns: select_cols.append(codigo_sede_col)
            if numero_sede_col and numero_sede_col in ips_servicio.columns: select_cols.append(numero_sede_col)
            if nombre_sede_col and nombre_sede_col in ips_servicio.columns: select_cols.append(nombre_sede_col)
            if 'Departamento' in ips_servicio.columns: select_cols.append('Departamento')
            if 'Municipio' in ips_servicio.columns: select_cols.append('Municipio')
            if 'num nivel atencion' in ips_servicio.columns: select_cols.append('num nivel atencion')
            if servicio_used in ips_servicio.columns: select_cols.append(servicio_used)
            tabla_sedes_servicio = ips_servicio.loc[:, select_cols].rename(columns={servicio_used:'Descripción del servicio'})

            # PRIORIDAD: sumar 'num cantidad capacidad instalada' por sede_id+servicio si existe
            units_map = {}
            if 'num cantidad capacidad instalada' in ips_rows.columns:
                try:
                    units_series = ips_rows.groupby(['sede_id', servicio_used])['num cantidad capacidad instalada'].sum()
                    units_map = {(str(k[0]), str(k[1])): int(v) for k, v in units_series.items()}
                except Exception:
                    units_map = {}

            counts_map = {}
            try:
                counts_series = ips_rows.groupby(['sede_id', servicio_used]).size()
                counts_map = {(str(k[0]), str(k[1])): int(v) for k, v in counts_series.items()}
            except Exception:
                counts_map = {}

            def get_qty(row):
                key = (str(row.get('sede_id','')), str(row.get('Descripción del servicio','')))
                if units_map.get(key, 0) > 0:
                    return units_map.get(key, 0)
                return counts_map.get(key, 0)

            tabla_sedes_servicio['Cantidad del servicio'] = tabla_sedes_servicio.apply(get_qty, axis=1).astype(int)

            # expected_daily base using standards
            expected_daily_list = []
            matched_list = []
            debug_list = []
            for _, r in tabla_sedes_servicio.reset_index(drop=True).iterrows():
                svc_text = str(r.get('Descripción del servicio',''))
                std = find_standard_for_service(svc_text)
                key = (str(r.get('sede_id','')), svc_text)
                units = units_map.get(key, 0)
                if units == 0:
                    units = int(r.get('Cantidad del servicio', 0))
                if std is not None and units > 0:
                    expected_daily = round(units * float(std['daily_per_unit']), 1)
                    expected_daily_list.append(expected_daily)
                    matched_list.append(std['matched_key'])
                    debug_list.append(f"Matched: {std['matched_key']}")
                else:
                    base_count = int(r.get('Cantidad del servicio', 0))
                    if base_count == 0:
                        base_count = 1
                    s_lower = svc_text.lower()
                    if any(k in s_lower for k in ['camas','camillas','cuna','incubadora']):
                        scale = 0.18
                    elif any(k in s_lower for k in ['sala','quirófano','quirofano']):
                        scale = 5.0
                    else:
                        scale = 10.0
                    expected_daily_list.append(round(base_count * scale, 1))
                    matched_list.append(None)
                    debug_list.append(f"Fallback scale={scale}")

            tabla_sedes_servicio['_expected_daily_base'] = expected_daily_list
            tabla_sedes_servicio['_matched_standard_key'] = matched_list
            tabla_sedes_servicio['_debug'] = debug_list

            tabla_sedes_servicio = tabla_sedes_servicio.drop_duplicates(subset=['sede_id','Descripción del servicio','Cantidad del servicio']).reset_index(drop=True)
            def make_label(r):
                code = str(r.get(codigo_sede_col,'')) if codigo_sede_col in r.index else ""
                num = str(r.get(numero_sede_col,'')) if numero_sede_col in r.index else ""
                name = str(r.get(nombre_sede_col,'')) if nombre_sede_col in r.index else ""
                if code and num:
                    return f"{code}|{num} - {name}" if name else f"{code}|{num}"
                if code:
                    return f"{code} - {name}" if name else code
                if name:
                    return name
                return str(r.get('sede_id',''))
            tabla_sedes_servicio['_label'] = tabla_sedes_servicio.apply(make_label, axis=1)
            st.dataframe(tabla_sedes_servicio, use_container_width=True)
        else:
            st.info("Selecciona al menos un servicio para ver sedes que lo prestan.")

        # --------------------
        # SIMULACIÓN
        # --------------------
        st.subheader("Simulación de capacidad de atención")
        if tabla_sedes_servicio.empty:
            st.info("No hay filas para simular.")
            return

        sede_unique_df = tabla_sedes_servicio.drop_duplicates(subset=['sede_id']).reset_index(drop=True)
        sede_options = sede_unique_df['_label'].tolist()
        sede_key_map = { row['_label']: row['sede_id'] for _, row in sede_unique_df.iterrows() }
        sede_options_with_all = ["TODAS"] + sorted(sede_options)
        sede_seleccionada = st.selectbox("Selecciona sede (o TODAS):", options=sede_options_with_all, index=0)

        factor_operativo = filters.get("factor_operativo", 1.0)

        if sede_seleccionada == "TODAS":
            sim_rows = tabla_sedes_servicio.copy().reset_index(drop=True)
        else:
            sid = sede_key_map.get(sede_seleccionada)
            sim_rows = tabla_sedes_servicio[tabla_sedes_servicio['sede_id'].astype(str) == str(sid)].copy()

        daily_list = []; weekly_list = []; monthly_list = []
        for _, row in sim_rows.iterrows():
            svc = str(row.get('Descripción del servicio',''))
            expected_base = row.get('_expected_daily_base', None)
            seed = hash_seed(nit_norm, row.get('sede_id',''), svc)
            rng = np.random.default_rng(seed)
            noise = rng.normal(loc=1.0, scale=0.05)
            utilization = max(0.1, factor_operativo * noise)

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

            weekly_est = daily_est * 7
            monthly_est = daily_est * 30
            daily_list.append(daily_est); weekly_list.append(weekly_est); monthly_list.append(monthly_est)

        sim_rows = sim_rows.reset_index(drop=True)
        sim_rows['Usuarios diarios estimados'] = daily_list
        sim_rows['Usuarios semanales estimados'] = weekly_list
        sim_rows['Usuarios mensuales estimados'] = monthly_list

        # Normalize Nivel column in simulation display if present as 'num nivel atencion'
        if 'num nivel atencion' in sim_rows.columns:
            sim_rows = sim_rows.rename(columns={'num nivel atencion': 'Nivel'})

        preferred = ['sede_id','codigo_sede','numero_sede','Departamento','Municipio','Nivel','nombre_sede','_label','Descripción del servicio','Cantidad del servicio','_expected_daily_base','_debug','Usuarios diarios estimados','Usuarios semanales estimados','Usuarios mensuales estimados']
        sim_display = sim_rows.loc[:, [c for c in preferred if c in sim_rows.columns] + [c for c in sim_rows.columns if c not in preferred]]

        st.dataframe(sim_display, use_container_width=True)

        # Atenciones por sede
        group_key = '_label' if '_label' in sim_display.columns else ('sede_id' if 'sede_id' in sim_display.columns else None)
        if group_key:
            atenciones_por_sede = sim_display.groupby(group_key)[['Usuarios diarios estimados','Usuarios semanales estimados','Usuarios mensuales estimados']].sum().reset_index()
            atenciones_por_sede = atenciones_por_sede.sort_values('Usuarios diarios estimados', ascending=False).reset_index(drop=True)
            atenciones_por_sede = atenciones_por_sede.rename(columns={group_key:'Sede','Usuarios diarios estimados':'Atenciones diarias estimadas','Usuarios semanales estimados':'Atenciones semanales estimadas','Usuarios mensuales estimados':'Atenciones mensuales estimadas'})
            st.subheader("Atenciones por sede (sumadas)")
            st.dataframe(atenciones_por_sede, use_container_width=True)

        # Resumen extendido (totales por servicio & nivel & sedes)
        total_daily = int(sim_display['Usuarios diarios estimados'].sum()) if 'Usuarios diarios estimados' in sim_display.columns else 0
        total_weekly = int(sim_display['Usuarios semanales estimados'].sum()) if 'Usuarios semanales estimados' in sim_display.columns else 0
        total_monthly = int(sim_display['Usuarios mensuales estimados'].sum()) if 'Usuarios mensuales estimados' in sim_display.columns else 0

        servicios_totales = pd.DataFrame()
        if 'Descripción del servicio' in sim_display.columns and 'Usuarios diarios estimados' in sim_display.columns:
            servicios_totales = sim_display.groupby('Descripción del servicio')['Usuarios diarios estimados'].sum().reset_index().rename(columns={'Usuarios diarios estimados':'Total diarios estimados'}).sort_values('Total diarios estimados', ascending=False)

        nivel_col_for_summary = 'Nivel' if 'Nivel' in sim_display.columns else ('num nivel atencion' if 'num nivel atencion' in sim_display.columns else None)
        nivel_totales = pd.DataFrame()
        if nivel_col_for_summary is not None and 'Usuarios diarios estimados' in sim_display.columns:
            nivel_totales = sim_display.groupby(nivel_col_for_summary)['Usuarios diarios estimados'].sum().reset_index().rename(columns={'Usuarios diarios estimados':'Total diarios estimados'}).sort_values('Total diarios estimados', ascending=False)
            if nivel_col_for_summary != 'Nivel':
                nivel_totales = nivel_totales.rename(columns={nivel_col_for_summary: 'Nivel'})
        else:
            nivel_totales = pd.DataFrame(columns=['Nivel', 'Total diarios estimados'])

        if 'sede_id' in sim_display.columns:
            involved_sedes = int(sim_display['sede_id'].nunique())
        elif 'nombre_sede' in sim_display.columns:
            involved_sedes = int(sim_display['nombre_sede'].nunique())
        else:
            involved_sedes = int(sim_display.shape[0])

        # Build resumen table and include totals by nivel as explicit rows
        rows = [
            {'Métrica':'Cantidad de atenciones diarias','Total estimado': format_number(total_daily)},
            {'Métrica':'Cantidad de atenciones semanales','Total estimado': format_number(total_weekly)},
            {'Métrica':'Cantidad de atenciones mensuales','Total estimado': format_number(total_monthly)},
            {'Métrica':'Total de sedes analizadas','Total estimado': str(involved_sedes)},
        ]
        rows.append({'Métrica':'--- Totales por servicio (diarios) ---','Total estimado':''})
        for _, r in servicios_totales.iterrows():
            rows.append({'Métrica': f"Servicio: {r['Descripción del servicio']}", 'Total estimado': format_number(int(r['Total diarios estimados']))})

        rows.append({'Métrica':'--- Atenciones por Nivel de complejidad (diarios) ---','Total estimado':''})
        if not nivel_totales.empty:
            for _, r in nivel_totales.iterrows():
                nivel_val = r.get('Nivel', r.iloc[0]) if 'Nivel' in r.index else r.iloc[0]
                rows.append({'Métrica': f"Nivel {nivel_val}", 'Total estimado': format_number(int(r['Total diarios estimados']))})
        else:
            rows.append({'Métrica':'Nivel (no disponible)', 'Total estimado': ''})

        resumen_atenciones_ext = pd.DataFrame(rows)
        st.subheader("Resumen de atenciones estimadas (extendido)")
        st.table(resumen_atenciones_ext)

        # Detalle tables and download
        sheets = {
            "Resumen": pd.DataFrame({'Métrica':['Total Sedes','Total Departamentos','Total Municipios'], 'Valor':[int(sede_unicas.shape[0]) if not sede_unicas.empty else involved_sedes, int(ips_rows['Departamento'].nunique()) if 'Departamento' in ips_rows.columns else 0, int(ips_rows['Municipio'].nunique()) if 'Municipio' in ips_rows.columns else 0]}),
            "Sedes": sede_unicas,
            "Simulacion": sim_display
        }
        if 'atenciones_por_sede' in locals() and not atenciones_por_sede.empty:
            sheets["Atenciones_por_sede"] = atenciones_por_sede
        if not servicios_totales.empty:
            sheets["Totales_por_servicio"] = servicios_totales
        if not nivel_totales.empty:
            sheets["Totales_por_nivel"] = nivel_totales
        tables_comp.download_excel(sheets, filename=f"simulacion_radiografia_{nit_norm}.xlsx")

        # ---------------- Giro Directo: Giros 2025 vs Capacidad mensual ----------------
        st.subheader("Giros 2025 (mes a mes) vs Capacidad mensual del simulador")
        try:
            parquet_giro = get_giro_parquet_path()
            con = duckdb.connect(database=":memory:")
            nit_col = _find_nit_col_in_parquet(parquet_giro, con)
            if nit_col is None:
                st.warning("No se encontró una columna NIT reconocida en el archivo Giro.parquet. No se puede consultar giros por NIT.")
            else:
                year = 2025
                # Query monthly sums for 2025 for selected NIT
                sql_monthly_nit = f"""
                SELECT date_trunc('month', {quote_col('Fecha Giro')})::DATE AS mes,
                       SUM({quote_col('Valor Girado')}) AS suma
                FROM '{parquet_giro}'
                WHERE {quote_col(nit_col)} = {quote_val(nit_norm)} AND EXTRACT(year FROM {quote_col('Fecha Giro')}) = {int(year)}
                GROUP BY 1
                ORDER BY 1
                """
                df_giro_monthly = con.execute(sql_monthly_nit).fetchdf()
                months_2025 = pd.date_range(start=f'{year}-01-01', end=f'{year}-12-01', freq='MS')
                df_months = pd.DataFrame({'mes': months_2025})
                if df_giro_monthly is None or df_giro_monthly.empty:
                    df_giro_monthly = pd.DataFrame(columns=['mes','suma'])
                else:
                    df_giro_monthly['mes'] = pd.to_datetime(df_giro_monthly['mes']).dt.to_period('M').dt.to_timestamp()
                    df_giro_monthly['suma'] = df_giro_monthly['suma'].astype(float)
                df_merge = df_months.merge(df_giro_monthly, on='mes', how='left').fillna({'suma':0.0})
                df_merge['suma'] = df_merge['suma'].astype(float)

                # Capacity monthly: sum of Usuarios mensuales estimados from sim_rows
                if 'Usuarios mensuales estimados' in sim_rows.columns:
                    capacity_monthly_total = float(sim_rows['Usuarios mensuales estimados'].sum())
                else:
                    if 'Usuarios diarios estimados' in sim_rows.columns:
                        capacity_monthly_total = float(sim_rows['Usuarios diarios estimados'].sum() * 30)
                    else:
                        capacity_monthly_total = 0.0

                # For display, capacity considered constant per month (as currently simulated)
                df_merge['Capacidad mensual (atenciones)'] = capacity_monthly_total

                # COP per atencion = Giro (COP) / Capacidad (atenciones)
                def compute_cop_por_atencion(row):
                    cap = row['Capacidad mensual (atenciones)']
                    if cap and cap > 0 and row['suma'] and row['suma'] > 0:
                        return row['suma'] / cap
                    return 0.0

                df_merge['COP_por_atencion'] = df_merge.apply(compute_cop_por_atencion, axis=1)
                df_merge['Giro_millones'] = df_merge['suma'] / 1_000_000.0

                # Table for display (formatted: thousands separators, no decimals)
                df_table = df_merge[['mes','Giro_millones','Capacidad mensual (atenciones)','COP_por_atencion']].copy()
                df_table = df_table.rename(columns={
                    'mes':'Mes',
                    'Giro_millones':'Giro (millones COP)',
                    'Capacidad mensual (atenciones)':'Capacidad mensual (atenciones)',
                    'COP_por_atencion':'Giro / Capacidad (COP por atención)'
                })
                # Create a formatted version for display (no decimals, thousands separator)
                df_display_formatted = df_table.copy()
                # Giro (millones) rounded to integer, show thousands and " M" suffix
                df_display_formatted['Giro (millones COP)'] = df_display_formatted['Giro (millones COP)'].round().astype(int).apply(lambda x: f"{x:,} M")
                df_display_formatted['Capacidad mensual (atenciones)'] = df_display_formatted['Capacidad mensual (atenciones)'].round().astype(int).apply(lambda x: f"{x:,}")
                df_display_formatted['Giro / Capacidad (COP por atención)'] = df_display_formatted['Giro / Capacidad (COP por atención)'].round().astype(int).apply(lambda x: f"${x:,}")
                df_display_formatted['Mes'] = df_display_formatted['Mes'].dt.strftime('%b %Y')

                st.dataframe(df_display_formatted, use_container_width=True)

                # Chart: show only COP per attention as bars (less clutter than dual axis)
                df_plot = df_table.copy()
                df_plot['Mes'] = df_plot['Mes'].dt.strftime('%b %Y')
                # build custom data for hover: Giro (millones numeric) and Capacity
                custom_data = np.stack([df_plot['Giro (millones COP)'].values, df_plot['Capacidad mensual (atenciones)'].values], axis=1)

                fig = px.bar(
                    df_plot,
                    x='Mes',
                    y='Giro / Capacidad (COP por atención)',
                    labels={'Giro / Capacidad (COP por atención)':'COP por atención', 'Mes':'Mes'},
                    title=f"Giro/Capacidad (COP por atención) por mes — NIT {nit_norm}"
                )
                # format y-axis ticks with thousand separators
                fig.update_yaxes(tickformat=",", title_text="COP por atención")
                # attach customdata and set hovertemplate to show Giro (millones) and capacity as well
                fig.update_traces(customdata=custom_data,
                                  hovertemplate="<b>%{x}</b><br>COP por atención: $%{y:,.0f}<br>Giro: %{customdata[0]:,.0f} M<br>Capacidad: %{customdata[1]:,}<extra></extra>",
                                  marker_color='firebrick')
                # remove text labels to avoid clutter/overlap
                fig.update_traces(textposition=None, texttemplate=None)

                st.plotly_chart(fig, use_container_width=True)

                # ---------- KPI YTD: promedio acumulado Giro/Capacidad (COP por atención) ----------
                try:
                    # Determinar mes final para el cálculo YTD:
                    # usar el mes actual, pero no ir más allá del último mes presente en df_merge
                    current_month = pd.to_datetime('today').to_period('M').to_timestamp()
                    last_data_month = df_merge['mes'].max() if 'mes' in df_merge.columns else current_month
                    end_month = min(current_month, last_data_month)

                    # Seleccionar meses desde enero del año hasta end_month
                    year_start = pd.Timestamp(year=end_month.year, month=1, day=1)
                    mask_ytd = (df_merge['mes'] >= year_start) & (df_merge['mes'] <= end_month)

                    # Número de meses considerados (p. ej. si hoy es 2025-10-20 → meses = 10)
                    months_considered = int(df_merge.loc[mask_ytd].shape[0])

                    # Total giro y capacidad en el periodo YTD
                    total_giro_ytd = float(df_merge.loc[mask_ytd, 'suma'].sum()) if months_considered > 0 else 0.0
                    total_capacity_ytd = float(capacity_monthly_total) * months_considered if months_considered > 0 else 0.0

                    # KPI: COP por atención acumulado YTD (defensivo)
                    if total_capacity_ytd and total_capacity_ytd > 0:
                        avg_cop_ytd = total_giro_ytd / total_capacity_ytd
                        avg_cop_fmt = f"${int(round(avg_cop_ytd)):,}"
                        avg_note = f"Promedio YTD ({year_start.strftime('%b %Y')} → {end_month.strftime('%b %Y')}) — {months_considered} mes(es) considerados"
                    else:
                        avg_cop_ytd = None
                        avg_cop_fmt = "N/A"
                        avg_note = "No hay capacidad registrada para calcular promedio YTD"

                    # Mostrar KPI grande (rectángulo)
                    kpi_html = f"""
                    <div style="border:1px solid #e3e3e3; padding:18px; border-radius:10px; background:linear-gradient(90deg,#ffffff,#fbfbfb); margin-top:18px;">
                      <div style="font-size:13px; color:#666;">KPI — Promedio Giro / Capacidad (COP por atención)</div>
                      <div style="font-size:44px; font-weight:700; color:#b22222; margin-top:6px;">{avg_cop_fmt}</div>
                      <div style="font-size:12px; color:#444; margin-top:6px;">{avg_note} — NIT {nit_norm}</div>
                    </div>
                    """
                    st.markdown(kpi_html, unsafe_allow_html=True)
                except Exception:
                    # don't block page if KPI fails
                    pass

        except Exception:
            tb = traceback.format_exc()
            _log_and_show(tb)
            # continue (don't break the page)

    except Exception:
        tb = traceback.format_exc()
        _log_and_show(tb)
        return
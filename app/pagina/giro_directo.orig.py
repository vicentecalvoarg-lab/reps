"""
Giro Directo — página integrada en el dashboard modular.

Versión completa y consolidada de la página Giro Directo, integrada como
app.pagina.giro_directo. Incluye:

- Conexión DuckDB en memoria (caché por sesión).
- Helpers seguros para mostrar DataFrames (safe_display_df).
- Gráficos: series mensuales, top N, agrupaciones dinámicas, treemap.
- Panel de Inspección de Registros Individuales:
    - muestra primero comparación últimos 6 meses vs mismos 6 meses año anterior
    - luego pie "EPS que pagan" y gráfico apilado por régimen
    - descarga CSV de resultados de inspección
- Export CSV para los datos filtrados (COPY desde DuckDB).
- Uso de variable de entorno GIRO_PARQUET para ruta al parquet (por defecto c:/evaluagiro/BD/Giro.parquet)
- Todas las widgets de la página usan keys con prefijo 'giro_' para evitar colisiones.
- Agrupaciones dinámicas: incluye opciones "Regimen (Circulo)" y "Naturaleza Jurídica (Barras)".
"""
from pathlib import Path
from datetime import date
from typing import List, Tuple, Optional
import os
import tempfile
import traceback

import streamlit as st
import pandas as pd
import plotly.express as px
import duckdb

# ---------------- Helpers ----------------

def safe_display_df(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    for c in df2.columns:
        if pd.api.types.is_object_dtype(df2[c]) or pd.api.types.is_categorical_dtype(df2[c]):
            df2[c] = df2[c].astype(str).fillna('')
    return df2

def format_money_int(x):
    try:
        if pd.isna(x):
            return ""
        return f"${int(round(float(x))):,}"
    except Exception:
        return str(x)

def format_millions_no_dec(x):
    """
    Formatea un valor ya expresado en millones (p. ej. 2.35 => "2 M" o "2.4 M").
    - Si el valor absoluto es >= 1 muestra sin decimales (redondeado a entero) y M.
    - Si es menor que 1 muestra con 2 decimales (ej. 0.45 M).
    Nota: esta función NO divide por 1_000_000; asume que el caller ya pasó el valor en millones.
    """
    try:
        if pd.isna(x):
            return ""
        val = float(x)
        if abs(val) >= 1:
            return f"{int(round(val)):,} M"
        # mostrar con 2 decimales cuando es menor a 1 millón (ej. 0.45 M)
        return f"{val:.2f} M"
    except Exception:
        return str(x)

def format_pct(x):
    try:
        if x is None or pd.isna(x):
            return "N/A"
        return f"{float(x):.2f} %"
    except Exception:
        return "N/A"

def quote_col(col: str) -> str:
    return f'"{col}"'

def quote_val(val: Optional[str]) -> str:
    if val is None:
        return "NULL"
    s = str(val).replace("'", "''")
    return f"'{s}'"

# ---------------- DuckDB connection and parquet path ----------------

@st.cache_resource(show_spinner=False)
def make_duckdb_connection():
    # In-memory DB reused during the session
    return duckdb.connect(database=":memory:")

def get_parquet_path() -> str:
    p = os.environ.get("GIRO_PARQUET")
    if p:
        return p
    # default path - adjust if needed
    return r"c:/evaluagiro/BD/Giro.parquet"

# ---------------- Query helpers (cached) ----------------

@st.cache_data(show_spinner=False)
def get_distinct_values(column: str, parquet_path: str) -> List[str]:
    con = make_duckdb_connection()
    sql = f"SELECT DISTINCT {quote_col(column)} AS val FROM '{parquet_path}' WHERE {quote_col(column)} IS NOT NULL ORDER BY 1"
    df = con.execute(sql).fetchdf()
    return df['val'].tolist() if not df.empty else []

@st.cache_data(show_spinner=False)
def get_distinct_values_where(column: str, base_where: str, parquet_path: str) -> List[str]:
    con = make_duckdb_connection()
    sql = f"SELECT DISTINCT {quote_col(column)} AS val FROM '{parquet_path}' WHERE {base_where} AND {quote_col(column)} IS NOT NULL ORDER BY 1"
    df = con.execute(sql).fetchdf()
    return df['val'].tolist() if not df.empty else []

@st.cache_data(show_spinner=False)
def get_date_bounds(parquet_path: str) -> Tuple[date, date]:
    con = make_duckdb_connection()
    sql = f"SELECT MIN({quote_col('Fecha Giro')}) AS min_fecha, MAX({quote_col('Fecha Giro')}) AS max_fecha FROM '{parquet_path}'"
    row = con.execute(sql).fetchone()
    if row and row[0] is not None:
        return pd.to_datetime(row[0]).date(), pd.to_datetime(row[1]).date()
    today = date.today()
    return today, today

@st.cache_data(show_spinner=False)
def query_monthly(where_clause: str, parquet_path: str) -> pd.DataFrame:
    con = make_duckdb_connection()
    sql = f"""
    SELECT date_trunc('month', {quote_col('Fecha Giro')})::DATE AS mes,
           SUM({quote_col('Valor Girado')}) AS suma
    FROM '{parquet_path}'
    WHERE {where_clause}
    GROUP BY 1
    ORDER BY 1
    """
    return con.execute(sql).fetchdf()

@st.cache_data(show_spinner=False)
def query_top_prestadores(where_clause: str, n_top: int, parquet_path: str) -> pd.DataFrame:
    con = make_duckdb_connection()
    sql = f"""
    SELECT {quote_col('Nombre Prestador')} AS nombre, SUM({quote_col('Valor Girado')}) AS suma
    FROM '{parquet_path}'
    WHERE {where_clause}
    GROUP BY 1
    ORDER BY suma DESC
    LIMIT {int(n_top)}
    """
    return con.execute(sql).fetchdf()

@st.cache_data(show_spinner=False)
def query_grouped_raw(where_clause: str, group_by: str, parquet_path: str) -> pd.DataFrame:
    con = make_duckdb_connection()
    sql = f"""
    SELECT {quote_col(group_by)} AS grupo, SUM({quote_col('Valor Girado')}) AS suma
    FROM '{parquet_path}'
    WHERE {where_clause}
    GROUP BY 1
    ORDER BY suma DESC
    """
    return con.execute(sql).fetchdf()

def query_treemap_eps_ips_with_where(where_clause: str, parquet_path: str) -> pd.DataFrame:
    con = make_duckdb_connection()
    sql = f"""
    SELECT {quote_col('EPS')} AS eps,
           {quote_col('Nombre Prestador')} AS nombre,
           SUM({quote_col('Valor Girado')}) AS valor
    FROM '{parquet_path}'
    WHERE {where_clause}
    GROUP BY 1,2
    """
    return con.execute(sql).fetchdf()

def query_treemap_filtered(where_clause: str, min_percent: float, max_percent: float, parquet_path: str) -> pd.DataFrame:
    con = make_duckdb_connection()
    sql = f"""
    WITH eps_ips AS (
      SELECT {quote_col('EPS')} AS eps,
             {quote_col('Nombre Prestador')} AS nombre,
             SUM({quote_col('Valor Girado')}) AS valor
      FROM '{parquet_path}'
      WHERE {where_clause}
      GROUP BY 1,2
    ),
    eps_totals AS (
      SELECT eps, SUM(valor) AS total_eps
      FROM eps_ips
      GROUP BY 1
    ),
    ranked AS (
      SELECT
        e.eps,
        e.nombre,
        e.valor,
        t.total_eps,
        SUM(e.valor) OVER (PARTITION BY e.eps ORDER BY e.valor DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumsum
      FROM eps_ips e
      JOIN eps_totals t USING (eps)
    )
    SELECT eps, nombre, valor, total_eps, cumsum,
           (cumsum / NULLIF(total_eps,0)) * 100.0 AS cumpercent
    FROM ranked
    WHERE (cumsum / NULLIF(total_eps,0)) * 100.0 >= {float(min_percent)} AND (cumsum / NULLIF(total_eps,0)) * 100.0 <= {float(max_percent)}
    ORDER BY eps, cumpercent
    """
    return con.execute(sql).fetchdf()

def inspect_records(search_type: str, search_value: str, start_date: date, end_date: date, parquet_path: str, limit: int = 10000) -> pd.DataFrame:
    if not search_value:
        return pd.DataFrame()
    sv = search_value.replace("'", "''")
    sd = start_date.strftime('%Y-%m-%d')
    ed = end_date.strftime('%Y-%m-%d')
    con = make_duckdb_connection()
    sql = f"""
    SELECT *
    FROM '{parquet_path}'
    WHERE {quote_col(search_type)} = '{sv}'
      AND {quote_col('Fecha Giro')} >= DATE '{sd}' AND {quote_col('Fecha Giro')} <= DATE '{ed}'
    LIMIT {int(limit)}
    """
    return con.execute(sql).fetchdf()

def export_filtered_to_csv(where_clause: str, parquet_path: str) -> str:
    con = make_duckdb_connection()
    sql_select = f"SELECT * FROM '{parquet_path}' WHERE {where_clause}"
    tf = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
    tf.close()
    out_path = tf.name
    con.execute(f"COPY ({sql_select}) TO '{out_path}' (HEADER, DELIMITER ',')")
    return out_path

# ---------------- Page entrypoint ----------------

def run(filters: dict, df_filtered: pd.DataFrame, df_all: pd.DataFrame):
    """
    Entry point called by app/main.py with signature run(filters, df_filtered, df_all).
    """
    parquet_path = get_parquet_path()

    # Protect set_page_config because main.py already sets page config for the app.
    try:
        st.set_page_config(layout="wide", page_title="Giro Directo ADRES")
    except Exception:
        pass

    st.sidebar.header('Giro Directo — Filtros (página)')
    # Distinct values for filters
    try:
        eps_values = get_distinct_values('EPS', parquet_path)
        dept_values = get_distinct_values('Departamento', parquet_path)
        mun_values = get_distinct_values('Municipio', parquet_path)
        reg_values = get_distinct_values('Regimen', parquet_path)
        nat_values = get_distinct_values('Naturaleza', parquet_path)
    except Exception as e:
        st.error(f"No se pudieron obtener los valores distintos desde el parquet: {e}")
        return

    unique_eps = ['TODOS'] + sorted([v for v in eps_values if pd.notna(v)])
    unique_dept = ['TODOS'] + sorted([v for v in dept_values if pd.notna(v)])
    unique_mun = ['TODOS'] + sorted([v for v in mun_values if pd.notna(v)])
    unique_reg = ['TODOS'] + sorted([v for v in reg_values if pd.notna(v)])
    unique_nat = ['TODOS'] + sorted([v for v in nat_values if pd.notna(v)])

    selected_eps = st.sidebar.selectbox('EPS', unique_eps, index=0, key='giro_eps')
    selected_dept = st.sidebar.selectbox('Departamento', unique_dept, index=0, key='giro_dept')
    selected_mun = st.sidebar.selectbox('Municipio', unique_mun, index=0, key='giro_mun')
    selected_reg = st.sidebar.selectbox('Régimen', unique_reg, index=0, key='giro_reg')
    selected_nat = st.sidebar.selectbox('Naturaleza Jurídica', unique_nat, index=0, key='giro_nat')

    # Date range (sidebar)
    try:
        min_date, max_date = get_date_bounds(parquet_path)
    except Exception:
        min_date, max_date = date.today(), date.today()

    selected_dates = st.sidebar.date_input(
        'Rango de Fechas (Fecha Giro)',
        [min_date, max_date],
        min_value=min_date,
        max_value=max_date,
        key='giro_dates'
    )

    # Normalize date_input
    if isinstance(selected_dates, (list, tuple)):
        if len(selected_dates) == 2:
            start_date, end_date = selected_dates
        elif len(selected_dates) == 1:
            start_date = end_date = selected_dates[0]
        else:
            start_date, end_date = min_date, max_date
    else:
        start_date = end_date = selected_dates

    def build_where(selected_eps, selected_dept, selected_mun, selected_reg, selected_nat, start_date, end_date) -> str:
        where = []
        if selected_eps and selected_eps != 'TODOS':
            where.append(f"{quote_col('EPS')} = {quote_val(selected_eps)}")
        if selected_dept and selected_dept != 'TODOS':
            where.append(f"{quote_col('Departamento')} = {quote_val(selected_dept)}")
        if selected_mun and selected_mun != 'TODOS':
            where.append(f"{quote_col('Municipio')} = {quote_val(selected_mun)}")
        if selected_reg and selected_reg != 'TODOS':
            where.append(f"{quote_col('Regimen')} = {quote_val(selected_reg)}")
        if selected_nat and selected_nat != 'TODOS':
            where.append(f"{quote_col('Naturaleza')} = {quote_val(selected_nat)}")
        if start_date and end_date:
            sd = start_date.strftime('%Y-%m-%d')
            ed = end_date.strftime('%Y-%m-%d')
            where.append(f"{quote_col('Fecha Giro')} >= DATE '{sd}' AND {quote_col('Fecha Giro')} <= DATE '{ed}'")
        return " AND ".join(where) if where else "1=1"

    base_where = build_where(selected_eps, selected_dept, selected_mun, selected_reg, selected_nat, start_date, end_date)
    period_text = f"Período: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"
    eps_display_name = selected_eps if selected_eps != 'TODOS' else "Red Completa (todas las EPS)"

    st.title('Dashboard de Análisis de Giro Directo ADRES (DuckDB)')

    # ---------------- Monthly Sum as Bar Chart ----------------
    st.header('Series Temporales: Suma Mensual de Valor Girado (en millones)')
    try:
        monthly_df = query_monthly(base_where, parquet_path)
    except Exception as e:
        st.error(f"Error consultando series mensuales: {e}")
        monthly_df = pd.DataFrame()

    if not monthly_df.empty:
        monthly_df['suma_millones'] = monthly_df['suma'] / 1_000_000.0
        monthly_df['label_millones'] = monthly_df['suma_millones'].apply(lambda x: f"{x:,.0f} M")
        monthly_df = monthly_df.sort_values('mes')
        title_month = f"Suma Mensual de Valor Girado - {period_text} - EPS: {eps_display_name}"
        fig_month = px.bar(monthly_df, x='mes', y='suma_millones',
                           labels={'suma_millones':'Valor (millones COP)', 'mes':'Mes'},
                           title=title_month)
        fig_month.update_traces(text=monthly_df['label_millones'], textposition='outside', marker_color='royalblue')
        fig_month.update_layout(yaxis_tickformat=',.0f', xaxis_tickformat='%Y-%m')
        st.plotly_chart(fig_month, use_container_width=True)
    else:
        st.write('No hay datos para el rango seleccionado.')

    # ---------------- Top N Prestadores ----------------
    st.header('Top N Prestadores por Valor Girado')
    n_top = st.slider('Seleccione N', min_value=5, max_value=50, value=10, key='giro_topn')
    try:
        top_prestadores = query_top_prestadores(base_where, n_top, parquet_path)
    except Exception as e:
        st.error(f"Error consultando top prestadores: {e}")
        top_prestadores = pd.DataFrame()

    if not top_prestadores.empty:
        names_order = top_prestadores['nombre'].tolist()
        top_prestadores_sorted = top_prestadores.sort_values('suma', ascending=True)
        title_top = f"Top {n_top} Prestadores por Valor Girado - {period_text} - EPS: {eps_display_name}"
        fig_top = px.bar(top_prestadores_sorted, x='suma', y='nombre', orientation='h', title=title_top)
        fig_top.update_layout(yaxis={'categoryorder':'array', 'categoryarray': list(reversed(names_order))})
        fig_top.update_traces(marker_color='steelblue')
        fig_top.update_xaxes(tickformat=',.0f')
        st.plotly_chart(fig_top, use_container_width=True)
    else:
        st.write('No hay datos para mostrar.')

    # ---------------- Dynamic Groupings ----------------
    st.header('Agrupaciones Dinámicas')
    # Añadimos las dos opciones solicitadas: Regimen (Circulo) y Naturaleza Jurídica (Barras)
    group_by_options = ['Departamento', 'Municipio', 'EPS', 'Nombre Prestador', 'Regimen (Circulo)', 'Naturaleza Jurídica (Barras)']
    selected_group = st.selectbox('Agrupar por', group_by_options, key='giro_group_by')

    st.markdown("Seleccione rango de % acumulado de monto girado para filtrar la agrupación (orden descendente por suma).")
    min_percent_group = st.slider('Porcentaje Acumulado Mínimo (%) - Agrupaciones', 0, 100, 0, key='giro_group_min')
    max_percent_group = st.slider('Porcentaje Acumulado Máximo (%) - Agrupaciones', 0, 100, 100, key='giro_group_max')

    # Mapear la opción visible a la columna real del parquet
    if selected_group.startswith('Regimen'):
        group_col = 'Regimen'
    elif selected_group.startswith('Naturaleza'):
        group_col = 'Naturaleza'
    else:
        group_col = selected_group

    try:
        grouped_raw = query_grouped_raw(base_where, group_col, parquet_path)
    except Exception as e:
        st.error(f"Error consultando agrupaciones: {e}")
        grouped_raw = pd.DataFrame()

    if grouped_raw is None or grouped_raw.empty:
        st.write('No hay datos para la agrupación seleccionada.')
    else:
        grouped_raw = grouped_raw.rename(columns={'grupo':'grupo', 'suma':'suma'}).sort_values('suma', ascending=False).reset_index(drop=True)
        prev_start = (pd.to_datetime(start_date) - pd.DateOffset(years=1)).date()
        prev_end = (pd.to_datetime(end_date) - pd.DateOffset(years=1)).date()
        prev_where = build_where(selected_eps, selected_dept, selected_mun, selected_reg, selected_nat, prev_start, prev_end)
        try:
            grouped_prev = query_grouped_raw(prev_where, group_col, parquet_path)
        except Exception:
            grouped_prev = pd.DataFrame(columns=['grupo', 'suma'])
        grouped_prev = grouped_prev.rename(columns={'suma':'suma_prev'})
        merged = grouped_raw.merge(grouped_prev, on='grupo', how='left')
        merged['suma_prev'] = merged['suma_prev'].fillna(0.0)
        total_sum = merged['suma'].sum()
        merged['cum_sum'] = merged['suma'].cumsum()
        merged['cum_percent'] = merged['cum_sum'] / total_sum * 100.0 if total_sum > 0 else 0.0
        filtered_group = merged[(merged['cum_percent'] >= min_percent_group) & (merged['cum_percent'] <= max_percent_group)].copy()

        if not filtered_group.empty:
            # Visualizaciones según el tipo pedido por el usuario
            title_grp = f"Suma de Valor Girado por {group_col} (Filtrado por % acumulado {min_percent_group}% - {max_percent_group}%) - {period_text} - EPS: {eps_display_name}"

            if group_col == 'Regimen':
                # Mostrar como pie (círculo)
                fg = filtered_group.copy()
                fg['suma_millones'] = fg['suma'] / 1_000_000.0
                # Pie con label mostrando millones + %
                fg['label_millones'] = fg['suma_millones'].apply(lambda x: format_millions_no_dec(x))
                fig_pie = px.pie(fg, names='grupo', values='suma', title=title_grp, hole=0)
                fig_pie.update_traces(text=fg['label_millones'], textposition='inside',
                                      hovertemplate='<b>%{label}</b><br>Valor: %{value:,.0f} COP<br>%{percent:.2%}<extra></extra>')
                st.plotly_chart(fig_pie, use_container_width=True)
                # Mostrar tabla resumida
                display_for_show = pd.DataFrame({
                    group_col: fg['grupo'].astype(str),
                    'Suma Valor Girado (millones)': fg['suma_millones'].apply(lambda x: format_millions_no_dec(x)),
                    'Valor Año Anterior': fg['suma_prev'].apply(lambda x: format_money_int(x)),
                    '% Acumulado': fg['cum_percent'].apply(lambda x: f"{x:.2f} %")
                })
                st.dataframe(safe_display_df(display_for_show))
            elif group_col == 'Naturaleza':
                # Mostrar como barras
                fg = filtered_group.copy()
                fg['suma_millones'] = fg['suma'] / 1_000_000.0
                fg_plot = fg.sort_values('suma', ascending=True)
                fig_bar_nat = px.bar(fg_plot, x='suma_millones', y='grupo', orientation='h', title=title_grp,
                                     labels={'suma_millones':'Valor (millones COP)', 'grupo':'Naturaleza Jurídica'})
                fig_bar_nat.update_traces(marker_color='darkorange')
                fig_bar_nat.update_layout(xaxis_tickformat=',.0f')
                st.plotly_chart(fig_bar_nat, use_container_width=True)

                display_for_show = pd.DataFrame({
                    'Naturaleza Jurídica': fg_plot['grupo'].astype(str),
                    'Suma Valor Girado (millones)': fg_plot['suma_millones'].apply(lambda x: format_millions_no_dec(x)),
                    'Valor Año Anterior': fg_plot['suma_prev'].apply(lambda x: format_money_int(x)),
                    '% Acumulado': fg_plot['cum_percent'].apply(lambda x: f"{x:.2f} %")
                })
                st.dataframe(safe_display_df(display_for_show))
            else:
                # Default: barras horizontales por grupo (comportamiento previo)
                fg = filtered_group.copy()
                fg_plot = fg.sort_values('suma', ascending=True)
                title_default = f"Suma de Valor Girado por {group_col} (Filtrado por % acumulado {min_percent_group}% - {max_percent_group}%) - {period_text} - EPS: {eps_display_name}"
                fig_grp = px.bar(fg_plot, x='suma', y='grupo', orientation='h', title=title_default)
                fig_grp.update_traces(marker_color='seagreen')
                fig_grp.update_xaxes(tickformat=',.0f')
                st.plotly_chart(fig_grp, use_container_width=True)

                display_for_show = pd.DataFrame({
                    group_col: fg_plot['grupo'].astype(str),
                    'Suma Valor Girado': fg_plot['suma'].apply(lambda x: format_money_int(x)),
                    'Valor Año Anterior': fg_plot['suma_prev'].apply(lambda x: format_money_int(x)),
                    '% Acumulado': fg_plot['cum_percent'].apply(lambda x: f"{x:.2f} %")
                })
                st.dataframe(safe_display_df(display_for_show))
        else:
            st.write('No hay grupos dentro del rango de % acumulado seleccionado.')

    # ---------------- Table export ----------------
    st.header('Tabla de Datos Filtrados')
    st.markdown(f"Datos filtrados para EPS: {eps_display_name} - {period_text}")
    if st.button('Generar CSV para descarga', key='giro_gen_csv'):
        with st.spinner('Generando CSV...'):
            try:
                csv_path = export_filtered_to_csv(base_where, parquet_path)
                with open(csv_path, 'rb') as f:
                    st.download_button('Descargar CSV filtrado', f, file_name=f"datos_filtrados_giro_{eps_display_name.replace(' ', '_')}.csv", mime='text/csv', key='giro_download_csv')
                try:
                    os.unlink(csv_path)
                except Exception:
                    pass
            except Exception as e:
                st.error(f"Ocurrió un error al generar el CSV: {e}")

    # ---------------- Treemap Section ----------------
    st.header('Análisis de Redes EPS-IPS como Mapa de Rectángulos')
    st.subheader('Distribución de Valor Girado por EPS e IPS')
    st.markdown(f"**EPS evaluada:** {eps_display_name}")

    try:
        treemap_depts = ['TODOS'] + sorted([v for v in get_distinct_values_where('Departamento', base_where, parquet_path) if pd.notna(v)])
        treemap_muns = ['TODOS'] + sorted([v for v in get_distinct_values_where('Municipio', base_where, parquet_path) if pd.notna(v)])
        treemap_regs = ['TODOS'] + sorted([v for v in get_distinct_values_where('Regimen', base_where, parquet_path) if pd.notna(v)])
    except Exception:
        treemap_depts = ['TODOS']; treemap_muns = ['TODOS']; treemap_regs = ['TODOS']

    col_a, col_b, col_c = st.columns([1,1,1])
    with col_a:
        sel_tm_dept = st.selectbox('Departamento (Mapa)', treemap_depts, index=0, key='giro_tm_dept')
    with col_b:
        sel_tm_mun = st.selectbox('Municipio (Mapa)', treemap_muns, index=0, key='giro_tm_mun')
    with col_c:
        sel_tm_reg = st.selectbox('Régimen (Mapa)', treemap_regs, index=0, key='giro_tm_reg')

    treemap_extra = []
    if sel_tm_dept and sel_tm_dept != 'TODOS':
        treemap_extra.append(f"{quote_col('Departamento')} = {quote_val(sel_tm_dept)}")
    if sel_tm_mun and sel_tm_mun != 'TODOS':
        treemap_extra.append(f"{quote_col('Municipio')} = {quote_val(sel_tm_mun)}")
    if sel_tm_reg and sel_tm_reg != 'TODOS':
        treemap_extra.append(f"{quote_col('Regimen')} = {quote_val(sel_tm_reg)}")

    treemap_where = base_where
    if treemap_extra:
        treemap_where = f"({base_where}) AND (" + " AND ".join(treemap_extra) + ")"

    min_percent = st.slider('Porcentaje Acumulado Mínimo (%)', 0, 100, 0, key='giro_map_min')
    max_percent = st.slider('Porcentaje Acumulado Máximo (%)', 0, 100, 20, key='giro_map_max')

    try:
        eps_ips_full = query_treemap_eps_ips_with_where(treemap_where, parquet_path)
        eps_ips_df = query_treemap_filtered(treemap_where, min_percent, max_percent, parquet_path)
    except Exception as e:
        st.error(f"Error generando treemap: {e}")
        eps_ips_full = pd.DataFrame(); eps_ips_df = pd.DataFrame()

    if not eps_ips_df.empty:
        eps_ips_df['valor_millones'] = eps_ips_df['valor'] / 1_000_000.0
        title_tm = f"Mapa de Rectángulos de Red EPS-IPS (Rango {min_percent}% - {max_percent}%) - {period_text} - EPS: {eps_display_name}"
        fig_treemap = px.treemap(
            eps_ips_df,
            path=['eps', 'nombre'],
            values='valor',
            color='valor',
            color_continuous_scale='Blues',
            custom_data=['valor_millones'],
            title=title_tm
        )
        fig_treemap.update_traces(
            texttemplate='%{label}<br>%{customdata[0]:,.0f} M',
            textposition='middle center',
            hovertemplate='<b>%{label}</b><br>Valor: %{customdata[0]:,.0f} M<br>%{percentRoot:.2%}<extra></extra>'
        )
        st.plotly_chart(fig_treemap, use_container_width=True)
    else:
        st.write('No hay datos en el rango de acumulación seleccionado para el treemap con los filtros aplicados.')

    # ---------------- Summary under treemap ----------------
    st.markdown(f"### Resumen del rango seleccionado (treemap) - EPS: {eps_display_name}")
    try:
        total_ips_in_range = int(eps_ips_df['nombre'].nunique()) if not eps_ips_df.empty else 0
        total_ips_all = int(eps_ips_full['nombre'].nunique()) if not eps_ips_full.empty else 0
        value_total_in_range = float(eps_ips_df['valor'].sum()) if not eps_ips_df.empty else 0.0
        value_total_all = float(eps_ips_full['valor'].sum()) if not eps_ips_full.empty else 0.0

        pct_ips_over_total = (total_ips_in_range / total_ips_all * 100.0) if total_ips_all > 0 else 0.0
        pct_value_over_total = (value_total_in_range / value_total_all * 100.0) if value_total_all > 0 else 0.0

        if not eps_ips_df.empty:
            eps_sorted = eps_ips_df.sort_values('valor', ascending=False).reset_index(drop=True)
            first_ips_val = float(eps_sorted.loc[0, 'valor']) if len(eps_sorted) > 0 else 0.0
            last_ips_val = float(eps_sorted.loc[len(eps_sorted)-1, 'valor']) if len(eps_sorted) > 0 else 0.0
        else:
            first_ips_val = 0.0
            last_ips_val = 0.0

        summary_rows = [
            {'Métrica': 'Total de IPS en el rango', 'Valor': total_ips_in_range},
            {'Métrica': '% de IPS sobre total en la red analizada', 'Valor': f"{pct_ips_over_total:.2f} %"},
            {'Métrica': 'Valor total girado en el rango', 'Valor': f"${value_total_in_range:,.0f}"},
            {'Métrica': '% del valor total girado en el rango', 'Valor': f"{pct_value_over_total:.2f} %"},
            {'Métrica': 'Valor Giro Primera IPS del rango', 'Valor': f"${first_ips_val:,.0f}"},
            {'Métrica': 'Valor Giro Ultima IPS del Rango', 'Valor': f"${last_ips_val:,.0f}"}
        ]
        summary_df = pd.DataFrame(summary_rows)
        st.table(safe_display_df(summary_df.astype(str)))
    except Exception as e:
        st.write("No fue posible calcular el resumen:", e)

    # ---------------- Panel de Inspección de Registros Individuales ----------------
    st.header('Panel de Inspección de Registros Individuales')
    st.markdown(f"EPS contexto de búsqueda: {eps_display_name} - {period_text}")

    search_type = st.radio('Buscar por', ['NIT', 'Nombre Prestador'], key='giro_search_type')
    search_value = st.text_input(f'Ingrese {search_type}', key='giro_search_value')

    inspect_dates = st.date_input('Rango de Fechas para Inspección', [start_date, end_date], min_value=min_date, max_value=max_date, key='giro_inspect_dates')

    if isinstance(inspect_dates, (list, tuple)):
        if len(inspect_dates) == 2:
            start_d, end_d = inspect_dates
        elif len(inspect_dates) == 1:
            start_d = end_d = inspect_dates[0]
        else:
            start_d, end_d = start_date, end_date
    else:
        start_d = end_d = inspect_dates

    if st.button('Buscar registros', key='giro_search_button'):
        with st.spinner('Buscando...'):
            try:
                inspect_df = inspect_records(search_type, search_value, start_d, end_d, parquet_path)
            except Exception as e:
                st.error(f"Error consultando registros: {e}")
                inspect_df = pd.DataFrame()

            if inspect_df is None or inspect_df.empty:
                st.write('No se encontraron registros para los criterios de búsqueda.')
            else:
                st.subheader('Registros encontrados')
                st.dataframe(safe_display_df(inspect_df))
                csv_bytes = inspect_df.to_csv(index=False).encode('utf-8')
                st.download_button('Descargar resultados de inspección (CSV)', csv_bytes, 'inspeccion_giro.csv', 'text/csv', key='giro_inspect_dl')

                # Determine provider name (razón social) to use in titles
                try:
                    if search_type == 'Nombre Prestador' and str(search_value).strip() != "":
                        provider_name = str(search_value)
                    else:
                        # Try to get from inspect_df column (case-insensitive)
                        cols_lower = {c.lower(): c for c in inspect_df.columns}
                        if 'nombre prestador' in cols_lower:
                            provider_name = str(inspect_df[cols_lower['nombre prestador']].dropna().astype(str).iloc[0])
                        elif 'nombre_prestador' in cols_lower:
                            provider_name = str(inspect_df[cols_lower['nombre_prestador']].dropna().astype(str).iloc[0])
                        elif 'nombre prestador ' in cols_lower:
                            provider_name = str(inspect_df[cols_lower['nombre prestador ']].dropna().astype(str).iloc[0])
                        else:
                            # fallback show search_value (likely NIT)
                            provider_name = str(search_value)
                except Exception:
                    provider_name = str(search_value)

                # Build SQL condition used by the inspection
                cond = f"{quote_col(search_type)} = {quote_val(search_value)} AND {quote_col('Fecha Giro')} >= DATE '{start_d.strftime('%Y-%m-%d')}' AND {quote_col('Fecha Giro')} <= DATE '{end_d.strftime('%Y-%m-%d')}'"
                con = make_duckdb_connection()

                # --- Replaced: comparison last 6 months vs same 6 months previous year ---
                try:
                    # End and start months (first day of month)
                    end_month = pd.to_datetime(end_d).replace(day=1)
                    start_month = (end_month - pd.DateOffset(months=5)).normalize()
                    prev_start_month = (start_month - pd.DateOffset(years=1))
                    prev_end_month = (end_month - pd.DateOffset(years=1))

                    cond_cur = f"{quote_col(search_type)} = {quote_val(search_value)} AND date_trunc('month', {quote_col('Fecha Giro')}) BETWEEN DATE '{start_month.strftime('%Y-%m-%d')}' AND DATE '{end_month.strftime('%Y-%m-%d')}'"
                    cond_prev = f"{quote_col(search_type)} = {quote_val(search_value)} AND date_trunc('month', {quote_col('Fecha Giro')}) BETWEEN DATE '{prev_start_month.strftime('%Y-%m-%d')}' AND DATE '{prev_end_month.strftime('%Y-%m-%d')}'"

                    sql_cur = f"""
                    SELECT date_trunc('month', {quote_col('Fecha Giro')})::DATE AS mes,
                           SUM({quote_col('Valor Girado')}) AS suma
                    FROM '{parquet_path}'
                    WHERE {cond_cur}
                    GROUP BY 1
                    ORDER BY 1
                    """
                    sql_prev = f"""
                    SELECT date_trunc('month', {quote_col('Fecha Giro')})::DATE AS mes,
                           SUM({quote_col('Valor Girado')}) AS suma
                    FROM '{parquet_path}'
                    WHERE {cond_prev}
                    GROUP BY 1
                    ORDER BY 1
                    """

                    df_cur = con.execute(sql_cur).fetchdf()
                    df_prev = con.execute(sql_prev).fetchdf()

                    months_idx = pd.date_range(start=start_month, periods=6, freq='MS')

                    if not df_cur.empty:
                        df_cur['suma'] = df_cur['suma'].astype(float)
                        df_cur['mes'] = pd.to_datetime(df_cur['mes']).dt.to_period('M').dt.to_timestamp()
                    if not df_prev.empty:
                        df_prev['suma'] = df_prev['suma'].astype(float)
                        df_prev['mes'] = pd.to_datetime(df_prev['mes']).dt.to_period('M').dt.to_timestamp()

                    cur_map = {pd.to_datetime(r['mes']): float(r['suma']) for _, r in df_cur.iterrows()} if not df_cur.empty else {}
                    prev_map = {pd.to_datetime(r['mes']): float(r['suma']) for _, r in df_prev.iterrows()} if not df_prev.empty else {}

                    rows = []
                    for m in months_idx:
                        cur_val = cur_map.get(m, 0.0)
                        prev_val = prev_map.get((m - pd.DateOffset(years=1)), 0.0)
                        rows.append({'mes': m, 'Periodo': cur_val, 'Periodo Año Anterior': prev_val})

                    df_compare = pd.DataFrame(rows)
                    df_melt = df_compare.melt(id_vars='mes', value_vars=['Periodo','Periodo Año Anterior'], var_name='PeriodoTipo', value_name='suma')
                    df_melt['suma_millones'] = df_melt['suma'] / 1_000_000.0

                    # Title rendered via markdown for reliable line breaks and centering
                    title_html = f"Comparación: últimos 6 meses ({start_month.strftime('%b %Y')} → {end_month.strftime('%b %Y')}) vs año anterior<br><strong>{provider_name}</strong> — EPS: <strong>{eps_display_name}</strong>"
                    st.markdown(f"<div style='text-align:center; margin-bottom:8px'>{title_html}</div>", unsafe_allow_html=True)

                    if not df_melt.empty:
                        df_melt['mes_label'] = df_melt['mes'].dt.strftime('%b %Y')
                        # Crear la figura pasando text='suma_millones' para que cada barra use su propio valor
                        fig_inspect_month = px.bar(
                            df_melt,
                            x='mes_label',
                            y='suma_millones',
                            color='PeriodoTipo',
                            barmode='group',
                            labels={'suma_millones':'Valor (millones COP)', 'mes_label':'Mes', 'PeriodoTipo':'Periodo'},
                            text='suma_millones',
                            title=''
                        )
                        # Formato del texto dentro de las barras (1 decimal) y posición
                        fig_inspect_month.update_traces(texttemplate='%{text:,.1f} M', textposition='inside')
                        fig_inspect_month.update_layout(yaxis_tickformat=',.0f', legend_title_text='Periodo')
                        st.plotly_chart(fig_inspect_month, use_container_width=True)

                        total_cur = df_compare['Periodo'].sum()
                        total_prev = df_compare['Periodo Año Anterior'].sum()
                        pct_change_total = ((total_cur - total_prev) / total_prev * 100.0) if total_prev not in (0, None) else None

                        resumen = [
                            {'Métrica': f"Total {start_month.strftime('%b %Y')}→{end_month.strftime('%b %Y')}",
                             'Periodo actual': format_money_int(total_cur),
                             'Periodo anterior': format_money_int(total_prev),
                             '% Variación': (f"{pct_change_total:.2f} %" if pct_change_total is not None else "N/A")}
                        ]
                        st.table(pd.DataFrame(resumen))
                    else:
                        st.write("No hay movimientos en los periodos solicitados para generar la comparación.")
                except Exception as e:
                    st.error(f"Error generando comparación 6 meses vs año anterior: {e}")

                # --- Pie chart: EPS que pagan (robusto, independiente) ---
                try:
                    # Asegurarnos de tener la conexión y la condición definidas
                    try:
                        cond  # noqa: F821
                    except NameError:
                        cond = f"{quote_col(search_type)} = {quote_val(search_value)} AND {quote_col('Fecha Giro')} >= DATE '{start_d.strftime('%Y-%m-%d')}' AND {quote_col('Fecha Giro')} <= DATE '{end_d.strftime('%Y-%m-%d')}'"

                    sql_eps_payers = f"""
                    SELECT {quote_col('EPS')} AS eps, SUM({quote_col('Valor Girado')}) AS suma
                    FROM '{parquet_path}'
                    WHERE {cond}
                    GROUP BY 1
                    ORDER BY suma DESC
                    """
                    df_eps_payers = con.execute(sql_eps_payers).fetchdf()

                    # Mostrar título con provider + EPS (ya mostrado antes, se puede repetir)
                    title_html = f"Pago por Régimen para: <strong>{provider_name}</strong><br>Nombre de la EPS: <strong>{eps_display_name}</strong>"
                    st.markdown(f"<div style='text-align:center; margin-bottom:6px'>{title_html}</div>", unsafe_allow_html=True)

                    if df_eps_payers is not None and not df_eps_payers.empty:
                        # Prepara columnas en millones para etiquetas
                        df_eps_payers['suma'] = df_eps_payers['suma'].astype(float)
                        df_eps_payers['suma_millones'] = df_eps_payers['suma'] / 1_000_000.0
                        df_eps_payers['suma_millones_fmt'] = df_eps_payers['suma_millones'].apply(lambda x: format_millions_no_dec(x))
                        total_eps_pay = df_eps_payers['suma'].sum()
                        df_eps_payers['pct'] = df_eps_payers['suma'] / total_eps_pay * 100.0

                        # Pie: mostrar label compuesto (millones + %)
                        df_eps_payers['label'] = df_eps_payers.apply(lambda r: f"{r['suma_millones_fmt']}<br>{r['pct']:.2f}%", axis=1)
                        st.subheader('EPS que pagan al prestador (por Valor Girado)')
                        fig_eps_pie = px.pie(df_eps_payers, values='suma', names='eps', hole=0)
                        fig_eps_pie.update_traces(text=df_eps_payers['label'], textposition='inside', textinfo='text',
                                                  hovertemplate='<b>%{label}</b><br>Valor: %{value:,.0f} COP<br>%{percent:.2%}<extra></extra>')
                        st.plotly_chart(fig_eps_pie, use_container_width=True)
                    else:
                        st.info('No se encontraron EPS que paguen en el rango de fechas para el criterio buscado.')
                except Exception as e:
                    st.error(f"Error al generar gráfico de EPS pagadoras: {e}")

                # --- Stacked bar chart by Regimen (apilado por EPS) ---
                try:
                    sql_regimen_eps = f"""
                    SELECT {quote_col('Regimen')} AS regimen,
                           {quote_col('EPS')} AS eps,
                           SUM({quote_col('Valor Girado')}) AS suma
                    FROM '{parquet_path}'
                    WHERE {cond}
                    GROUP BY 1,2
                    ORDER BY 1,3 DESC
                    """
                    df_reg_eps = con.execute(sql_regimen_eps).fetchdf()
                    if df_reg_eps is not None and not df_reg_eps.empty:
                        df_reg_eps['suma'] = df_reg_eps['suma'].astype(float)
                        df_reg_eps['suma_millones'] = df_reg_eps['suma'] / 1_000_000.0
                        total_by_reg = df_reg_eps.groupby('regimen')['suma_millones'].sum().rename('total_reg').reset_index()
                        df_long = df_reg_eps.merge(total_by_reg, on='regimen', how='left')
                        df_long['pct'] = df_long.apply(lambda r: (r['suma_millones'] / r['total_reg'] * 100.0) if r['total_reg'] and r['total_reg'] > 0 else 0.0, axis=1)

                        LABEL_PCT_THRESHOLD = 3.0
                        df_long['label_segment'] = df_long.apply(
                            lambda r: f"{format_millions_no_dec(r['suma_millones'])}\n{r['pct']:.2f}%" if r['pct'] >= LABEL_PCT_THRESHOLD else "",
                            axis=1
                        )

                        st.subheader('Distribución del pago por Régimen (apilado por EPS)')
                        fig_stack = px.bar(
                            df_long,
                            x='regimen',
                            y='suma_millones',
                            color='eps',
                            labels={'suma_millones':'Valor (millones COP)', 'regimen':'Régimen', 'eps':'EPS'},
                            custom_data=['eps','suma_millones','pct','label_segment']
                        )
                        fig_stack.update_layout(barmode='stack', xaxis_tickangle=-45, legend_title_text='EPS')
                        fig_stack.update_traces(
                            texttemplate='%{customdata[3]}',
                            textposition='inside',
                            hovertemplate='<b>%{customdata[0]}</b><br>Régimen: %{x}<br>Valor: %{customdata[1]:,.0f} M<br>Participación: %{customdata[2]:.2f}%'
                        )
                        fig_stack.update_yaxes(title='Valor (millones COP)')
                        st.plotly_chart(fig_stack, use_container_width=True)
                    else:
                        st.info('No se encontraron registros por Régimen/EPS para el criterio buscado en el periodo.')
                except Exception as e:
                    st.error(f"Error al generar gráfico apilado por régimen: {e}")

                # --- EPS summary table current vs previous year (optional) ---
                try:
                    if 'df_eps_payers' in locals() and df_eps_payers is not None and not df_eps_payers.empty:
                        df_curr = df_eps_payers.rename(columns={'eps':'EPS','suma':'ValorPeriodo'})[['EPS','ValorPeriodo']].copy()
                    else:
                        df_curr = pd.DataFrame(columns=['EPS','ValorPeriodo'])

                    prev_start_ins = (pd.to_datetime(start_d) - pd.DateOffset(years=1)).date()
                    prev_end_ins = (pd.to_datetime(end_d) - pd.DateOffset(years=1)).date()
                    cond_prev = f"{quote_col(search_type)} = {quote_val(search_value)} AND {quote_col('Fecha Giro')} >= DATE '{prev_start_ins.strftime('%Y-%m-%d')}' AND {quote_col('Fecha Giro')} <= DATE '{prev_end_ins.strftime('%Y-%m-%d')}'"
                    sql_eps_prev = f"""
                    SELECT {quote_col('EPS')} AS eps, SUM({quote_col('Valor Girado')}) AS suma
                    FROM '{parquet_path}'
                    WHERE {cond_prev}
                    GROUP BY 1
                    ORDER BY suma DESC
                    """
                    df_eps_prev = con.execute(sql_eps_prev).fetchdf()
                    if df_eps_prev is None or df_eps_prev.empty:
                        df_prev = pd.DataFrame(columns=['EPS','ValorPeriodoAnterior'])
                    else:
                        df_prev = df_eps_prev.rename(columns={'eps':'EPS','suma':'ValorPeriodoAnterior'})[['EPS','ValorPeriodoAnterior']].copy()

                    merged_eps = pd.merge(df_curr, df_prev, on='EPS', how='outer').fillna(0.0)
                    merged_eps['% Variacion'] = merged_eps.apply(lambda r: ((r['ValorPeriodo'] - r['ValorPeriodoAnterior'])/r['ValorPeriodoAnterior']*100.0) if r['ValorPeriodoAnterior'] not in (0,None) else None, axis=1)

                    display_eps_tbl = pd.DataFrame({
                        'EPS': merged_eps['EPS'].astype(str),
                        f'Valor ({start_d.strftime("%d/%m/%Y")} - {end_d.strftime("%d/%m/%Y")})': merged_eps['ValorPeriodo'].apply(lambda x: format_money_int(x)),
                        f'Valor Año Anterior ({prev_start_ins.strftime("%d/%m/%Y")} - {prev_end_ins.strftime("%d/%m/%Y")})': merged_eps['ValorPeriodoAnterior'].apply(lambda x: format_money_int(x)),
                        '% Variación': merged_eps['% Variacion'].apply(lambda x: format_pct(x) if x is not None else "N/A")
                    })
                    st.subheader('Resumen por EPS para el prestador (Periodo vs Año Anterior)')
                    st.dataframe(safe_display_df(display_eps_tbl))
                except Exception:
                    pass

    # ---------------- Additional visuals (end of run) ----------------

    # Footer with last cut date
    try:
        latest = make_duckdb_connection().execute(f"SELECT MAX({quote_col('Fecha Giro')}) FROM '{parquet_path}'").fetchone()[0]
        latest_str = pd.to_datetime(latest).strftime('%d/%m/%Y') if latest is not None else 'N/A'
        st.caption(f"Fuente: ADRES BD Giro Directo - Corte: {latest_str} - EPS contexto: {eps_display_name}")
    except Exception:
        st.caption(f"Fuente: ADRES BD Giro Directo - EPS contexto: {eps_display_name}")
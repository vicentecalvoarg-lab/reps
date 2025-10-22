"""
Giro Directo — página integrada en el dashboard modular.

Adaptación con protección contra excepciones para debug:
- Muestra "DEBUG: entered giro_directo" al entrar en run
- Envuelve todo en try/except, muestra traceback en UI y lo escribe en C:/REPS/logs/giro_directo_error.log
- Protege set_page_config para evitar excepciones si ya se llamó en main
"""
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import duckdb
import tempfile
import traceback
from pathlib import Path
from datetime import date
from typing import List, Tuple

LOG_DIR = Path("C:/REPS/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "giro_directo_error.log"

def _log_and_show(tb_text: str):
    st.error("Se produjo una excepción en la página 'Giro Directo'. Ver detalles abajo.")
    st.exception(tb_text)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(tb_text)
            f.write("\n\n")
    except Exception:
        pass

def quote_col(col: str) -> str:
    return f'"{col}"'

def quote_val(val: str) -> str:
    if val is None:
        return "NULL"
    s = str(val).replace("'", "''")
    return f"'{s}'"

# DuckDB connection cached resource
@st.cache_resource(show_spinner=False)
def make_duckdb_connection():
    return duckdb.connect(database=':memory:')

def get_parquet_path() -> str:
    p = os.environ.get("GIRO_PARQUET")
    if p:
        return p
    # default path used previously; adjust if needed
    return r"c:/evaluagiro/BD/Giro.parquet"

# helper query functions
@st.cache_data(show_spinner=False)
def get_distinct_values(column: str, parquet_path: str) -> List[str]:
    con = make_duckdb_connection()
    sql = f"SELECT DISTINCT {quote_col(column)} AS val FROM '{parquet_path}' WHERE {quote_col(column)} IS NOT NULL ORDER BY 1"
    df = con.execute(sql).fetchdf()
    return df['val'].tolist() if not df.empty else []

@st.cache_data(show_spinner=False)
def get_date_bounds(parquet_path: str):
    con = make_duckdb_connection()
    sql = f"SELECT MIN({quote_col('Fecha Giro')}) AS min_fecha, MAX({quote_col('Fecha Giro')}) AS max_fecha FROM '{parquet_path}'"
    row = con.execute(sql).fetchone()
    if row and row[0] is not None:
        return pd.to_datetime(row[0]).date(), pd.to_datetime(row[1]).date()
    today = date.today()
    return today, today

@st.cache_data(show_spinner=False)
def query_monthly(where_clause: str, parquet_path: str):
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

# (otros helpers análogos pueden definirse aquí según necesidad; se pueden añadir con try/except)

def run(filters: dict, df_filtered: pd.DataFrame, df_all: pd.DataFrame):
    st.write("DEBUG: entered giro_directo")
    try:
        parquet_path = get_parquet_path()
        # Protect set_page_config in case main already set it
        try:
            st.set_page_config(layout="wide", page_title="Giro Directo ADRES")
        except Exception:
            # ignore: set_page_config can only be called once per app
            pass

        st.sidebar.header('Giro Directo — Filtros (página)')
        # Build distinct values
        eps_values = get_distinct_values('EPS', parquet_path)
        dept_values = get_distinct_values('Departamento', parquet_path)
        mun_values = get_distinct_values('Municipio', parquet_path)
        reg_values = get_distinct_values('Regimen', parquet_path)
        nat_values = get_distinct_values('Naturaleza', parquet_path)

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

        min_date, max_date = get_date_bounds(parquet_path)
        selected_dates = st.sidebar.date_input(
            'Rango de Fechas (Fecha Giro)',
            [min_date, max_date],
            min_value=min_date,
            max_value=max_date,
            key='giro_dates'
        )

        # ensure date normalization
        if isinstance(selected_dates, (list, tuple)):
            if len(selected_dates) == 2:
                start_date, end_date = selected_dates
            elif len(selected_dates) == 1:
                start_date = end_date = selected_dates[0]
            else:
                start_date, end_date = min_date, max_date
        else:
            start_date = end_date = selected_dates

        def build_where(selected_eps, selected_dept, selected_mun, selected_reg, selected_nat, start_date, end_date):
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

        # Example: monthly series
        st.header('Series Temporales: Suma Mensual de Valor Girado (en millones)')
        monthly_df = query_monthly(base_where, parquet_path)
        if not monthly_df.empty:
            monthly_df['suma_millones'] = monthly_df['suma'] / 1_000_000.0
            monthly_df = monthly_df.sort_values('mes')
            title_month = f"Suma Mensual de Valor Girado - {period_text} - EPS: {eps_display_name}"
            fig_month = px.bar(monthly_df, x='mes', y='suma_millones', labels={'suma_millones':'Valor (millones COP)', 'mes':'Mes'}, title=title_month)
            st.plotly_chart(fig_month, use_container_width=True)
        else:
            st.write('No hay datos para el rango seleccionado.')

        # ... (la página puede contener el resto del contenido original)
        # Para mantener la página liviana en el debug inicial, añadimos al final una confirmación:
        st.write("Giro Directo: ejecución completada (debug). Si esperabas más contenido, lo cargaremos luego.")

    except Exception:
        tb = traceback.format_exc()
        _log_and_show(tb)
        return
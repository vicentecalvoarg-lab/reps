"""
master_ips_01.py
Bloque 01: construir id_table (un registro por sede) y guardarlo en ctx.
Consume:
 - ctx['df_result']
Produce:
 - ctx['id_table']
 - ctx['outputs']['id_table']
"""
from typing import Dict, Any
import pandas as pd
import streamlit as st

def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    df = ctx.get("df_result")
    helpers = ctx.get("helpers", {})
    normalize = helpers.get("normalize")
    safe_str = helpers.get("safe_str")
    build_sede = helpers.get("build_sede_key")
    find_codigo = helpers.get("find_col")

    st.write("Bloque 01 — Construyendo tabla de identificación por sede")
    if df is None or df.empty:
        st.info("No hay datos en df_result para construir id_table.")
        ctx.setdefault("outputs", {})["id_table"] = pd.DataFrame()
        return ctx

    df_local = df.copy()
    # ensure nit_normalized exists
    df_local = helpers.get("ensure_nit")(df_local)

    # build sede key
    codigo_cols = [c for c in df_local.columns if "sede" in str(c).lower() and "cod" in str(c).lower()]
    sede_name_col = helpers.get("find_col")(df_local, ["nom sede", "nombre sede", "nom_sede"])
    dept_col = helpers.get("find_col")(df_local, ["departamento"])
    mun_col = helpers.get("find_col")(df_local, ["municipio"])
    df_local['_sede_key'] = build_sede(df_local, codigo_cols, sede_name_col, dept_col, mun_col)

    # choose columns to display
    prefer = []
    if 'nit_normalized' in df_local.columns:
        prefer.append('nit_normalized')
    if sede_name_col and sede_name_col in df_local.columns:
        prefer.append(sede_name_col)
    if dept_col and dept_col in df_local.columns:
        prefer.append(dept_col)
    if mun_col and mun_col in df_local.columns:
        prefer.append(mun_col)

    tmp = df_local.loc[:, ['_sede_key'] + prefer].drop_duplicates(subset=['_sede_key']).reset_index(drop=True)
    # rename columns for clarity
    rename_map = {}
    if 'nit_normalized' in tmp.columns:
        rename_map['nit_normalized'] = 'NIT'
    if sede_name_col in tmp.columns:
        rename_map[sede_name_col] = 'NOMBRE SEDE'
    if dept_col in tmp.columns:
        rename_map[dept_col] = 'DEPARTAMENTO'
    if mun_col in tmp.columns:
        rename_map[mun_col] = 'MUNICIPIO'
    id_table = tmp.rename(columns=rename_map)
    ctx['id_table'] = id_table
    ctx.setdefault("outputs", {})["id_table"] = id_table
    st.write(f"id_table: {len(id_table):,} sedes")
    if not id_table.empty:
        st.dataframe(id_table.head(50), use_container_width=True)
    return ctx
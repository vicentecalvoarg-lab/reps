"""
master_ips_02.py
Bloque 02: calcular servicios por escala (counts, TOTAL_OFERTA, POBLACION, INDICADOR_POR_ESCALA)

Consume:
 - ctx['df_result']
 - ctx['censo_path']

Produce:
 - ctx['outputs']['servicios_df']
 - ctx['per_sede_combo'] (para usar después)

Mejoras:
 - formatea TOTAL_OFERTA y POBLACION con separadores de miles para presentación
 - añade columna formateada del indicador con título que recuerda la escala usada
 - ordena la presentación de mayor TOTAL_OFERTA a menor TOTAL_OFERTA
"""
from typing import Dict, Any
import pandas as pd
import numpy as np
import streamlit as st

def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    df = ctx.get("df_result")
    helpers = ctx.get("helpers", {})
    normalize = helpers.get("normalize")
    build_sede = helpers.get("build_sede_key")
    find_col = helpers.get("find_col")
    load_censo = helpers.get("load_censo_csv")

    st.write("Bloque 02 — Calculando oferta por SERVICIO | ESPECIALIDAD y indicador por escala")
    if df is None or df.empty:
        st.info("No hay datos para calcular servicios.")
        ctx.setdefault("outputs", {})["servicios_df"] = pd.DataFrame()
        ctx['per_sede_combo'] = pd.DataFrame()
        return ctx

    # detectar columnas de servicio/especialidad
    svc_col = find_col(df, ["nom grupo capacidad", "servicio", "nom grupo", "grupo"])
    spec_col = find_col(df, ["nom descripcion capacidad", "especialidad", "descripcion"])

    # construir COMBO (clave interna)
    df_src = df.copy()
    if svc_col and spec_col:
        df_src['COMBO'] = df_src[svc_col].astype(str).fillna("").str.strip() + " | " + df_src[spec_col].astype(str).fillna("").str.strip()
    elif svc_col:
        df_src['COMBO'] = df_src[svc_col].astype(str).fillna("").str.strip()
    elif spec_col:
        df_src['COMBO'] = df_src[spec_col].astype(str).fillna("").str.strip()
    else:
        df_src['COMBO'] = df_src.index.astype(str)

    # asegurar COMBO como string y sin nulos
    df_src['COMBO'] = df_src['COMBO'].astype(str).fillna("").str.strip()

    # clave de sede
    codigo_cols = [c for c in df_src.columns if "sede" in str(c).lower() and "cod" in str(c).lower()]
    dept_col = find_col(df_src, ["departamento"])
    mun_col = find_col(df_src, ["municipio"])
    sede_name_col = find_col(df_src, ["nom sede", "nombre sede"])
    df_src['_sede_key'] = build_sede(df_src, codigo_cols, sede_name_col, dept_col, mun_col)

    # sedes únicas por combo
    if 'COMBO' not in df_src.columns:
        df_src['COMBO'] = df_src.index.astype(str)
    df_sedes_unique = df_src.drop_duplicates(subset=['_sede_key', 'COMBO']).reset_index(drop=True)

    # contar sedes por COMBO (clave interna)
    if 'COMBO' in df_sedes_unique.columns:
        sedes_counts = df_sedes_unique.groupby('COMBO', as_index=False)['_sede_key'].nunique().rename(columns={'_sede_key': 'SEDES_N'})
    else:
        df_sedes_unique['COMBO'] = df_sedes_unique.index.astype(str)
        sedes_counts = df_sedes_unique.groupby('COMBO', as_index=False)['_sede_key'].nunique().rename(columns={'_sede_key': 'SEDES_N'})

    # detectar columna de cantidad/oferta (mejor esfuerzo)
    def _find_quantity_col_local(df_local):
        for p in ["cantidad","cant","oferta","capacidad","cupos","puestos","total"]:
            col = find_col(df_local, [p])
            if col:
                return col
        return None
    qty_col = _find_quantity_col_local(df_src)

    per_sede_combo = pd.DataFrame()
    if qty_col:
        try:
            cleaned = df_src[qty_col].astype(str).fillna("").str.replace(r"[^\d\-\.,]", "", regex=True)
            df_src['_QTY_NUM'] = pd.to_numeric(cleaned.str.replace(",", "."), errors='coerce').fillna(0.0)
        except Exception:
            df_src['_QTY_NUM'] = pd.to_numeric(df_src[qty_col].astype(str).str.replace(r"[^\d\-\.,]", "", regex=True).str.replace(",", "."), errors='coerce').fillna(0.0)
        if df_src['_QTY_NUM'].sum() > 0:
            per_sede_combo = df_src.groupby(['_sede_key','COMBO'], as_index=False)['_QTY_NUM'].sum().rename(columns={'_QTY_NUM':'OFERTA_POR_SEDE'})

    # si no hay cantidades, usar presencia por sede-combo
    if per_sede_combo.empty:
        per_sede_combo = df_src.drop_duplicates(subset=['_sede_key','COMBO']).loc[:, ['_sede_key','COMBO']].copy()
        per_sede_combo['OFERTA_POR_SEDE'] = 1.0

    # total oferta por COMBO (clave interna)
    if 'COMBO' not in per_sede_combo.columns:
        per_sede_combo['COMBO'] = per_sede_combo.index.astype(str)
    total_offers = per_sede_combo.groupby('COMBO', as_index=False)['OFERTA_POR_SEDE'].sum().rename(columns={'OFERTA_POR_SEDE':'TOTAL_OFERTA'})
    total_offers['COMBO_NORM'] = total_offers['COMBO'].astype(str).str.strip()

    # merge usando COMBO (clave interna)
    if 'COMBO' in sedes_counts.columns:
        merged = sedes_counts.merge(total_offers, left_on='COMBO', right_on='COMBO', how='left')
    else:
        sedes_counts = sedes_counts.reset_index().rename(columns={'index':'COMBO'})
        merged = sedes_counts.merge(total_offers, left_on='COMBO', right_on='COMBO', how='left')

    # fallback si TOTAL_OFERTA es NaN: usar SEDES_N
    if 'TOTAL_OFERTA' not in merged.columns:
        merged['TOTAL_OFERTA'] = merged.get('SEDES_N', 0)
    else:
        merged['TOTAL_OFERTA'] = merged['TOTAL_OFERTA'].fillna(merged['SEDES_N'])

    # mantener COMBO (clave interna) y añadir columna de presentación 'SERVICIO | ESPECIALIDAD'
    merged['SERVICIO | ESPECIALIDAD'] = merged['COMBO'].astype(str)

    # construir servicios_df con COMBO (clave interna) y columna de display
    servicios_df = merged.loc[:, ['COMBO','SERVICIO | ESPECIALIDAD','SEDES_N','TOTAL_OFERTA']].copy()

    # compute population using census (mejor esfuerzo)
    censo = load_censo(ctx.get('censo_path')) if load_censo else None
    pop_map = {}
    mun_map = {}
    censo_work = pd.DataFrame()
    if censo is not None and not censo.empty:
        censo_dept_col = find_col(censo, ["departamento","CÓDIGO DIVIPOLA"])
        censo_mun_col = find_col(censo, ["municipio","NOMBRE MUNICIPIO"])
        censo_total_col = find_col(censo, ["TOTAL","POBLACION"])
        if censo_dept_col and censo_mun_col and censo_total_col:
            censo_work = censo[[censo_dept_col,censo_mun_col,censo_total_col]].copy()
            censo_work.columns = ["C_DEPT","C_MUN","C_TOTAL"]
            censo_work["C_DEPT_U"] = censo_work["C_DEPT"].astype(str).map(normalize)
            censo_work["C_MUN_U"] = censo_work["C_MUN"].astype(str).map(normalize)
            censo_work["C_TOTAL_NUM"] = pd.to_numeric(censo_work["C_TOTAL"].astype(str).str.replace(r"[^\d\-\.]","",regex=True), errors='coerce').fillna(0).astype(float)
            censo_work = censo_work.drop_duplicates(subset=["C_DEPT_U","C_MUN_U"])
            for _, r in censo_work.iterrows():
                pop_map.setdefault(r["C_DEPT_U"], {})[r["C_MUN_U"]] = r["C_TOTAL_NUM"]
            mun_map = censo_work.groupby("C_MUN_U")["C_TOTAL_NUM"].sum().to_dict()

    # calcular POBLACION por combo: iterar sobre la clave interna 'COMBO'
    pops = []
    for combo_key in servicios_df['COMBO'].astype(str).tolist():
        s_rows = df_src[df_src['COMBO'].astype(str).str.strip() == str(combo_key).strip()]
        if s_rows is None or s_rows.empty:
            pops.append(0.0)
            continue
        if 'DEPARTAMENTO' in s_rows.columns and 'MUNICIPIO' in s_rows.columns:
            depts = s_rows['DEPARTAMENTO'].astype(str).map(normalize).fillna("")
            muns = s_rows['MUNICIPIO'].astype(str).map(normalize).fillna("")
            pairs = pd.DataFrame({'D': depts, 'M': muns}).drop_duplicates()
        elif dept_col and mun_col and dept_col in df_src.columns and mun_col in df_src.columns:
            depts = s_rows[dept_col].astype(str).map(normalize).fillna("")
            muns = s_rows[mun_col].astype(str).map(normalize).fillna("")
            pairs = pd.DataFrame({'D': depts, 'M': muns}).drop_duplicates()
        else:
            pairs = pd.DataFrame(columns=['D','M'])
        pop_sum = 0.0
        if not pairs.empty and not censo_work.empty:
            for _, r in pairs.iterrows():
                D = r['D']; M = r['M']
                val = pop_map.get(D, {}).get(M, None)
                if val is None:
                    val = mun_map.get(M, 0)
                pop_sum += float(val or 0)
        pops.append(pop_sum)

    servicios_df['POBLACION'] = pops
    escala = int(ctx.get('display_options', {}).get('escala', 100000))
    servicios_df['INDICADOR_POR_ESCALA'] = servicios_df.apply(lambda r: (r['TOTAL_OFERTA'] / r['POBLACION'] * escala) if r['POBLACION']>0 else np.nan, axis=1)

    # ---------------- Presentation formatting and ordering ----------------
    # Keep numeric originals, add formatted columns for display
    # Format TOTAL_OFERTA and POBLACION with thousands separators
    servicios_df['TOTAL_OFERTA_NUM'] = pd.to_numeric(servicios_df['TOTAL_OFERTA'], errors='coerce').fillna(0)
    servicios_df['POBLACION_NUM'] = pd.to_numeric(servicios_df['POBLACION'], errors='coerce').fillna(0)

    servicios_df['TOTAL OFERTA'] = servicios_df['TOTAL_OFERTA_NUM'].map(lambda x: "{:,.0f}".format(x) if pd.notna(x) else "0")
    servicios_df['POBLACION (hab)'] = servicios_df['POBLACION_NUM'].map(lambda x: "{:,.0f}".format(x) if pd.notna(x) else "0")

    # Indicator display column label that includes the relation/scale
    indicador_label = f"OFERTA / {escala:,} hab."
    servicios_df[indicador_label] = servicios_df['INDICADOR_POR_ESCALA'].map(lambda x: "{:,.2f}".format(x) if pd.notna(x) else "N/A")

    # Sort by TOTAL_OFERTA numeric descending (may be what user expects: mayor oferta -> menor)
    servicios_df = servicios_df.sort_values('TOTAL_OFERTA_NUM', ascending=False).reset_index(drop=True)

    # Save outputs (servicios_df keeps numeric columns for downstream use)
    ctx.setdefault("outputs", {})["servicios_df"] = servicios_df
    ctx['per_sede_combo'] = per_sede_combo

    st.write(f"Indicador calculado como: TOTAL_OFERTA / POBLACION * {escala}")
    st.write(f"Bloque 02: {len(servicios_df):,} combos calculados (ordenados por TOTAL_OFERTA descendente)")
    # Present a friendly table with formatted columns
    display_cols = ['SERVICIO | ESPECIALIDAD', 'SEDES_N', 'TOTAL OFERTA', 'POBLACION (hab)', indicador_label]
    # ensure columns exist
    display_cols = [c for c in display_cols if c in servicios_df.columns]
    if display_cols:
        st.dataframe(servicios_df.loc[:, display_cols].head(int(ctx.get('filters', {}).get('MaxRows', 500))), use_container_width=True)
    else:
        st.dataframe(servicios_df.head(50), use_container_width=True)

    return ctx
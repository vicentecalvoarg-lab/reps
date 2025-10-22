"""
master_ips_04.py
Bloque 04: detalle por sede para la combinación seleccionada y pie chart.

Ajustes solicitados:
 - Mostrar separadores de miles en las cifras (OFERTA por sede, GIROS si aplica).
 - Incluir "NIVEL" (nivel de la IPS) como segunda columna de la tabla si se detecta.
 - Ordenar la tabla por OFERTA descendente (mayor a menor).
 - Mantener defensas frente a columnas faltantes.
"""
from typing import Dict, Any
import pandas as pd
import plotly.express as px
import streamlit as st


def _make_fallback_sede_key(row, helpers, dept_col=None, mun_col=None):
    # fallback: NIT|DEPARTAMENTO|MUNICIPIO
    safe_str = helpers.get("safe_str")
    clean_nit = helpers.get("clean_nit")
    nit = ""
    try:
        if 'nit_normalized' in row.index:
            nit = clean_nit(row['nit_normalized']) or ""
        elif 'nit' in row.index:
            nit = clean_nit(row['nit']) or ""
        else:
            nit = ""
    except Exception:
        nit = ""
    dept = ""
    mun = ""
    try:
        if dept_col and dept_col in row.index:
            dept = safe_str(pd.DataFrame([row]))[dept_col].iloc[0] if dept_col in row.index else ""
    except Exception:
        dept = ""
    try:
        if mun_col and mun_col in row.index:
            mun = safe_str(pd.DataFrame([row]))[mun_col].iloc[0] if mun_col in row.index else ""
    except Exception:
        mun = ""
    key = f"{nit}|{dept}|{mun}"
    return key


def _ensure_df(obj):
    # if obj is Series or Index or list, convert to DataFrame with single column
    if isinstance(obj, pd.DataFrame):
        return obj.copy()
    if isinstance(obj, pd.Series):
        return obj.to_frame().reset_index(drop=True)
    try:
        return pd.DataFrame(obj)
    except Exception:
        return pd.DataFrame()


def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    helpers = ctx.get("helpers", {})
    per_sede = ctx.get("per_sede_combo", pd.DataFrame())
    df_src = ctx.get("df_result", pd.DataFrame()).copy()
    st.write("Bloque 04 — Detalle por sede y gráfico circular")

    # normalize types
    per_sede = _ensure_df(per_sede)

    # If per_sede empty try to reconstruct from df_src (fallback)
    if per_sede.empty:
        st.info("per_sede_combo vacío: intento reconstruir desde df_result")
        if df_src is None or df_src.empty:
            st.info("df_result también vacío — no hay detalle por sede.")
            ctx.setdefault("outputs", {})["detalle_combo"] = pd.DataFrame()
            return ctx
        try:
            # Ensure nit_normalized exists
            try:
                if 'nit_normalized' not in df_src.columns:
                    df_src = helpers.get("ensure_nit")(df_src)
            except Exception:
                pass
            # Ensure COMBO exists
            if 'COMBO' not in df_src.columns:
                svc_col = helpers.get("find_col")(df_src, ["nom grupo capacidad", "servicio", "nom grupo", "grupo"])
                spec_col = helpers.get("find_col")(df_src, ["nom descripcion capacidad", "especialidad", "descripcion"])
                if svc_col and spec_col:
                    df_src['COMBO'] = df_src[svc_col].astype(str).fillna("") + " | " + df_src[spec_col].astype(str).fillna("")
                elif svc_col:
                    df_src['COMBO'] = df_src[svc_col].astype(str).fillna("")
                elif spec_col:
                    df_src['COMBO'] = df_src[spec_col].astype(str).fillna("")
                else:
                    df_src['COMBO'] = df_src.index.astype(str)
            # Ensure _sede_key exists, else create fallback
            if '_sede_key' not in df_src.columns:
                dept_col = helpers.get("find_col")(df_src, ["departamento"])
                mun_col = helpers.get("find_col")(df_src, ["municipio"])
                try:
                    df_src['_sede_key'] = df_src.apply(lambda r: _make_fallback_sede_key(r, helpers, dept_col, mun_col), axis=1)
                except Exception:
                    df_src['_sede_key'] = df_src.index.astype(str)
            per_sede = df_src.drop_duplicates(subset=['_sede_key', 'COMBO']).loc[:, ['_sede_key', 'COMBO']].copy()
            per_sede['OFERTA_POR_SEDE'] = 1.0
            st.success("Reconstruido per_sede_combo desde df_result (fallback).")
        except Exception as e:
            st.error(f"No se pudo reconstruir per_sede_combo: {e}")
            ctx.setdefault("outputs", {})["detalle_combo"] = pd.DataFrame()
            return ctx

    # Ensure per_sede has required columns
    if '_sede_key' not in per_sede.columns:
        per_sede['_sede_key'] = per_sede.index.astype(str)
    if 'COMBO' not in per_sede.columns:
        per_sede['COMBO'] = per_sede.get('COMBO', "").astype(str)
    if 'OFERTA_POR_SEDE' not in per_sede.columns:
        per_sede['OFERTA_POR_SEDE'] = 1.0

    # Ensure df_src has _sede_key; if not, create fallback
    if '_sede_key' not in df_src.columns:
        dept_col = helpers.get("find_col")(df_src, ["departamento"])
        mun_col = helpers.get("find_col")(df_src, ["municipio"])
        try:
            if 'nit_normalized' not in df_src.columns:
                df_src = helpers.get("ensure_nit")(df_src)
        except Exception:
            pass
        try:
            df_src['_sede_key'] = df_src.apply(lambda r: _make_fallback_sede_key(r, helpers, dept_col, mun_col), axis=1)
        except Exception:
            df_src['_sede_key'] = df_src.index.astype(str)

    # Build first_info dataframe with columns to join (if available), include NIVEL if present
    first_rows = df_src.drop_duplicates(subset=['_sede_key']).reset_index(drop=True) if not df_src.empty else pd.DataFrame()
    info_cols = []
    # detect possible level column names
    level_col = helpers.get("find_col")(df_src, ["nivel", "num nivel", "num nivel atencion", "nivel_atencion"])
    if level_col and level_col in first_rows.columns:
        info_cols.append(level_col)
    # nit and sede name
    if 'nit_normalized' in first_rows.columns:
        info_cols.append('nit_normalized')
    sede_name_col = helpers.get("find_col")(df_src, ["nom sede", "nombre sede"])
    if sede_name_col and sede_name_col in first_rows.columns:
        info_cols.append(sede_name_col)
    dept_col = helpers.get("find_col")(df_src, ["departamento"])
    mun_col = helpers.get("find_col")(df_src, ["municipio"])
    if dept_col and dept_col in first_rows.columns:
        info_cols.append(dept_col)
    if mun_col and mun_col in first_rows.columns:
        info_cols.append(mun_col)

    first_info = first_rows.loc[:, ['_sede_key'] + [c for c in info_cols if c in first_rows.columns]].copy()

    # Select combo to display
    combos = per_sede['COMBO'].astype(str).drop_duplicates().tolist()
    if not combos:
        st.info("No hay COMBOs disponibles en per_sede_combo.")
        ctx.setdefault("outputs", {})["detalle_combo"] = pd.DataFrame()
        return ctx

    selected_combo = st.selectbox("Seleccionar SERVICIO | ESPECIALIDAD para detalle", options=["(ninguno)"] + combos, index=0, key="detalle_combo_select_block")
    if not selected_combo or selected_combo == "(ninguno)":
        ctx.setdefault("outputs", {})["detalle_combo"] = pd.DataFrame()
        return ctx

    # select rows for the combo and merge with first_info
    try:
        sel_rows = per_sede[per_sede['COMBO'].astype(str).str.strip() == selected_combo].copy()
        if sel_rows.empty:
            st.info("No hay sedes para la combinación seleccionada.")
            ctx.setdefault("outputs", {})["detalle_combo"] = pd.DataFrame()
            return ctx
        if not first_info.empty:
            sel_rows = sel_rows.merge(first_info, on='_sede_key', how='left')
    except Exception as e:
        st.warning(f"Error al unir datos por '_sede_key': {e}. Mostraré per_sede sin join.")
        sel_rows = per_sede[per_sede['COMBO'].astype(str).str.strip() == selected_combo].copy()

    # GIROS por NIT (optional)
    nit_to_giros = {}
    giro_path = ctx.get("giro_path")
    if giro_path:
        try:
            gdf = helpers.get("load_giro_parquet")(giro_path)
            if gdf is not None and not gdf.empty:
                gdf = helpers.get("ensure_nit")(gdf)
                amount_col = helpers.get("find_col")(gdf, ["valor giro", "valor", "monto", "importe", "valor_total", "total"])
                if amount_col and amount_col in gdf.columns:
                    gdf['_amount'] = pd.to_numeric(gdf[amount_col], errors='coerce').fillna(0.0)
                else:
                    numeric_cols = [c for c in gdf.columns if pd.api.types.is_numeric_dtype(gdf[c])]
                    gdf['_amount'] = pd.to_numeric(gdf[numeric_cols[0]], errors='coerce').fillna(0.0) if numeric_cols else 0.0
                agg = gdf.groupby('nit_normalized', as_index=False)['_amount'].sum()
                agg['GIROS_MM'] = (agg['_amount'] / 1_000_000.0).round(0).astype(int)
                nit_to_giros = dict(zip(agg['nit_normalized'].astype(str), agg['GIROS_MM'].astype(int)))
        except Exception:
            nit_to_giros = {}

    # Prepare display dataframe
    disp = sel_rows.copy()

    # Determine the label/column name for NIVEL if present
    nivel_col_name = level_col if (level_col and level_col in disp.columns) else None
    if nivel_col_name is None:
        # try upper-case variants
        for c in disp.columns:
            if str(c).strip().lower() in ("nivel", "nivel de atención", "nivel_atencion", "num nivel", "num nivel atencion"):
                nivel_col_name = c
                break

    # Prepare columns to show and format numeric values
    # OFERTA per sede numeric: prefer OFERTA_POR_SEDE if present
    if 'OFERTA_POR_SEDE' in disp.columns:
        disp['OFERTA_POR_SEDE_NUM'] = pd.to_numeric(disp['OFERTA_POR_SEDE'], errors='coerce').fillna(0)
    else:
        # attempt to find a numeric offer column
        num_offer_cols = [c for c in disp.columns if any(k in str(c).lower() for k in ("oferta", "cantidad", "qty", "capacidad", "total")) and pd.api.types.is_numeric_dtype(disp[c])]
        if num_offer_cols:
            disp['OFERTA_POR_SEDE_NUM'] = pd.to_numeric(disp[num_offer_cols[0]], errors='coerce').fillna(0)
        else:
            disp['OFERTA_POR_SEDE_NUM'] = 1.0

    # Add GIROS if nit exists
    if 'nit_normalized' in disp.columns:
        try:
            disp['GIROS (MM COP)'] = disp['nit_normalized'].astype(str).map(lambda x: nit_to_giros.get(str(x), 0)).fillna(0).astype(int)
        except Exception:
            disp['GIROS (MM COP)'] = 0
    else:
        disp['GIROS (MM COP)'] = 0

    # Name column for display
    if sede_name_col and sede_name_col in disp.columns:
        disp = disp.rename(columns={sede_name_col: 'NOMBRE SEDE'})
        nombre_sede_col = 'NOMBRE SEDE'
    else:
        nombre_sede_col = None

    # Build final ordered display table with requested ordering: Nivel as second column, sort by oferta desc
    show_cols = []
    # First column: service combo (we show selected combo once; table is per sede so include NOMBRE SEDE)
    # Build columns sequence: NOMBRE SEDE (or _sede_key), NIVEL (if exist), SEDES? OFERTA, GIROS
    if nombre_sede_col:
        show_cols.append(nombre_sede_col)
    else:
        show_cols.append('_sede_key')

    # NIVEL as second column if available
    if nivel_col_name:
        show_cols.append(nivel_col_name)

    # OFERTA per sede and format
    show_cols += ['OFERTA_POR_SEDE_NUM', 'GIROS (MM COP)']

    # ensure columns exist
    show_cols = [c for c in show_cols if c in disp.columns]

    # Sort by oferta numeric descending
    if 'OFERTA_POR_SEDE_NUM' in disp.columns:
        disp = disp.sort_values('OFERTA_POR_SEDE_NUM', ascending=False).reset_index(drop=True)

    # Format numeric columns with thousands separators for display
    disp_display = disp.copy()
    if 'OFERTA_POR_SEDE_NUM' in disp_display.columns:
        disp_display['OFERTA'] = disp_display['OFERTA_POR_SEDE_NUM'].map(lambda x: "{:,.0f}".format(x) if pd.notna(x) else "0")
    else:
        disp_display['OFERTA'] = "0"

    if 'GIROS (MM COP)' in disp_display.columns:
        disp_display['GIROS (MM COP)'] = disp_display['GIROS (MM COP)'].map(lambda x: "{:,.0f}".format(x) if pd.notna(x) else "0")
    # prepare level display (keep original)
    if nivel_col_name and nivel_col_name in disp_display.columns:
        disp_display[nivel_col_name] = disp_display[nivel_col_name].astype(str)

    # final columns order for show: SERVICE (not necessary because the combo is selected), then NIVEL (if), NOMBRE SEDE/_sede_key, OFERTA, GIROS
    final_cols = []
    # place NOMBRE SEDE or key first
    if nombre_sede_col:
        final_cols.append(nombre_sede_col)
    else:
        final_cols.append('_sede_key')
    # nivel second if present
    if nivel_col_name and nivel_col_name in disp_display.columns:
        final_cols.append(nivel_col_name)
    # oferta & giros
    final_cols += ['OFERTA']
    if 'GIROS (MM COP)' in disp_display.columns:
        final_cols += ['GIROS (MM COP)']

    # ensure existence
    final_cols = [c for c in final_cols if c in disp_display.columns]

    # Highlight rows optionally (no special highlight requested here beyond earlier)
    def _highlight_low_row(row):
        return ['background-color: yellow' if False else "" for _ in row]

    # Show table
    if final_cols:
        try:
            st.dataframe(disp_display.loc[:, final_cols].reset_index(drop=True), use_container_width=True)
        except Exception:
            st.dataframe(disp_display.loc[:, final_cols].reset_index(drop=True))
    else:
        st.dataframe(disp_display.reset_index(drop=True), use_container_width=True)

    # Save outputs
    ctx.setdefault("outputs", {})["detalle_combo"] = disp

    return ctx
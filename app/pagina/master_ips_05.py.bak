"""
master_ips_05.py
Bloque 05: GIROS directos — resumen por NIT / Prestador

Mejoras aplicadas:
 - Añadido un menú desplegable con los nombres de las EPS para seleccionar una EPS
   específica para el treemap (además del filtro general de EPS para los giros).
 - Si se selecciona "TODAS" en el desplegable del treemap, se muestra la jerarquía
   EPS -> Prestadores; si se selecciona una EPS concreta, el treemap muestra los
   prestadores de esa EPS (rectángulos por prestador).
 - Conserva el control "Mostrar top N EPS en treemap (0 = todos)" para limitar EPS
   cuando se visualiza TODAS.
 - Mantiene el resto de la funcionalidad: filtro por EPS para los giros, Top N barras,
   tabla ordenada por giros, títulos y formato en millones.
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

    # EPS selector (global filter for giros)
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
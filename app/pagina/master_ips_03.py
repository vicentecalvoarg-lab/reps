"""
master_ips_03.py
Bloque 03: matching con sugeridos (prioriza XLSX), cálculo de métricas y presentación final.

Se corrigió el error KeyError 'CATEGORY' al filtrar por categoría:
 - la columna CATEGORY ahora se crea antes de filtrar los casos 'Bajo'
 - el selectbox usa la lista de categorías correctamente
 - se mantiene el gráfico de barras (solo casos 'Bajo') y la tabla formateada
"""
from typing import Dict, Any, Optional
from pathlib import Path
import pandas as pd
import numpy as np
import difflib
import re
import streamlit as st
import plotly.express as px

SUGERIDOS_XLSX = Path(r"C:/REPS/data/sugeridos.xlsx")
SUGERIDOS_CSV = Path(r"C:/REPS/data/sugeridos.csv")
MAPPINGS_PATH_XLSX = Path(r"C:/REPS/data/sugeridos_mappings.xlsx")
SUG_SHEET = "sugeridos"
MAP_SHEET = "mappings"

def _to_num(x) -> float:
    try:
        if pd.isna(x):
            return np.nan
        s = str(x).strip().replace(" ", "")
        if s.count(".") > 1 and "," in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            if "." in s and "," in s:
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", ".")
        s = "".join(ch for ch in s if ch.isdigit() or ch in ".-")
        return float(s) if s not in ("", "nan") else np.nan
    except Exception:
        return np.nan

def _norm_tokens(normalize_fn, text: str) -> str:
    if text is None:
        return ""
    t = re.sub(r"[\d]+", " ", str(text))
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return normalize_fn(t)

def _robust_read_csv(path: Path) -> pd.DataFrame:
    attempts = [
        {"sep":";", "encoding":"utf-8"},
        {"sep":";", "encoding":"latin1"},
        {"sep":",", "encoding":"utf-8"},
        {"sep":",", "encoding":"latin1"},
        {"sep": None, "engine":"python", "encoding":"utf-8"},
        {"sep": None, "engine":"python", "encoding":"latin1"},
    ]
    for a in attempts:
        try:
            df = pd.read_csv(str(path), **a)
            df.columns = [str(c).strip().replace("\ufeff","") for c in df.columns]
            if df.shape[1] >= 1:
                return df
        except Exception:
            continue
    try:
        df = pd.read_table(str(path), engine="python")
        df.columns = [str(c).strip().replace("\ufeff","") for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()

def _load_mappings() -> pd.DataFrame:
    if MAPPINGS_PATH_XLSX.exists():
        try:
            df = pd.read_excel(MAPPINGS_PATH_XLSX, sheet_name=MAP_SHEET, engine="openpyxl")
            df.columns = [str(c).strip() for c in df.columns]
            if "combo" in df.columns and "SERVICE_U" in df.columns:
                return df.loc[:, ["combo","SERVICE_U"]].drop_duplicates().reset_index(drop=True)
            if df.shape[1] >= 2:
                cols = df.columns[:2].tolist()
                df = df.rename(columns={cols[0]:"combo", cols[1]:"SERVICE_U"})
                return df.loc[:, ["combo","SERVICE_U"]].drop_duplicates().reset_index(drop=True)
        except Exception:
            return pd.DataFrame(columns=["combo","SERVICE_U"])
    return pd.DataFrame(columns=["combo","SERVICE_U"])

def _save_mapping_row(combo: str, service_u: str):
    try:
        new = pd.DataFrame([[combo, service_u]], columns=["combo","SERVICE_U"])
        if MAPPINGS_PATH_XLSX.exists():
            try:
                exist = pd.read_excel(MAPPINGS_PATH_XLSX, sheet_name=MAP_SHEET, engine="openpyxl")
                exist.columns = [str(c).strip() for c in exist.columns]
                if "combo" in exist.columns and "SERVICE_U" in exist.columns:
                    merged = pd.concat([exist, new], ignore_index=True)
                    merged = merged.drop_duplicates(subset=["combo"], keep="last").reset_index(drop=True)
                    with pd.ExcelWriter(MAPPINGS_PATH_XLSX, engine="openpyxl") as w:
                        merged.to_excel(w, sheet_name=MAP_SHEET, index=False)
                    return True
            except Exception:
                pass
        with pd.ExcelWriter(MAPPINGS_PATH_XLSX, engine="openpyxl") as w:
            new.to_excel(w, sheet_name=MAP_SHEET, index=False)
        return True
    except Exception as e:
        st.error(f"No se pudo guardar mapping: {e}")
        return False

def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    servicios_df = ctx.get("outputs", {}).get("servicios_df", pd.DataFrame()).copy()
    helpers = ctx.get("helpers", {})
    normalize = helpers.get("normalize")
    find_col = helpers.get("find_col")

    st.write("Bloque 03 — Matching con sugeridos y cálculo de métricas sugeridas")

    if servicios_df is None or servicios_df.empty:
        st.info("No hay servicios calculados para evaluar.")
        ctx.setdefault("outputs", {})["servicios_eval"] = pd.DataFrame()
        return ctx

    # 1) Cargar sugeridos (XLSX preferente, si no CSV)
    sugeridos_df = pd.DataFrame()
    loaded_from = None
    chosen_sheet = None
    if SUGERIDOS_XLSX.exists():
        try:
            xls = pd.ExcelFile(SUGERIDOS_XLSX, engine="openpyxl")
            sheets = xls.sheet_names
            target = None
            for s in sheets:
                if str(s).strip().lower() == SUG_SHEET.lower():
                    target = s
                    break
            if target is None and sheets:
                target = sheets[0]
            if target:
                sugeridos_df = pd.read_excel(SUGERIDOS_XLSX, sheet_name=target, engine="openpyxl")
                sugeridos_df.columns = [str(c).strip().replace("\ufeff","") for c in sugeridos_df.columns]
                loaded_from = f"{str(SUGERIDOS_XLSX)} (sheet: {target})"
                chosen_sheet = target
        except Exception:
            sugeridos_df = pd.DataFrame()

    if (sugeridos_df is None or sugeridos_df.empty) and SUGERIDOS_CSV.exists():
        sugeridos_df = _robust_read_csv(SUGERIDOS_CSV)
        if not sugeridos_df.empty:
            loaded_from = str(SUGERIDOS_CSV)

    # If not loaded, mark no benchmark
    if sugeridos_df is None or sugeridos_df.empty:
        servicios_df['SUG_KEY_MATCH'] = None
        servicios_df['SUG_MATCH_METHOD'] = None
        servicios_df['EVALUACIÓN (sugerido)'] = "No benchmark"
        servicios_df['VALOR SUGERIDO'] = np.nan
        servicios_df['DIF ABS'] = np.nan
        servicios_df['DESVIACIÓN (%)'] = np.nan
        ctx.setdefault("outputs", {})["servicios_eval"] = servicios_df
        display_df = pd.DataFrame({
            "SERVICIO | ESPECIALIDAD": servicios_df.get('SERVICIO | ESPECIALIDAD', servicios_df.get('COMBO', pd.Series(dtype=str))).astype(str),
            "SEDES": servicios_df.get('SEDES_N', pd.Series(dtype=float)).fillna(0).astype(int),
            "OFERTA": servicios_df.get('TOTAL_OFERTA_NUM', servicios_df.get('TOTAL_OFERTA', 0)).fillna(0).astype(float),
            "POBLACION": servicios_df.get('POBLACION_NUM', servicios_df.get('POBLACION', 0)).fillna(0).astype(float),
            "OFERTA X 100.000": servicios_df.get('INDICADOR_POR_ESCALA', servicios_df.get('INDICADOR_NUM', pd.Series([np.nan]*len(servicios_df)))),
            "EVALUACION": servicios_df.get('EVALUACIÓN (sugerido)', "No benchmark"),
            "VALOR SUGERIDO": servicios_df.get('VALOR SUGERIDO', np.nan),
        })
        display_df["SEDES"] = display_df["SEDES"].map(lambda x: "{:,.0f}".format(x))
        display_df["OFERTA"] = display_df["OFERTA"].map(lambda x: "{:,.0f}".format(x) if pd.notna(x) else "0")
        display_df["POBLACION"] = display_df["POBLACION"].map(lambda x: "{:,.0f}".format(x) if pd.notna(x) else "0")
        display_df["OFERTA X 100.000"] = display_df["OFERTA X 100.000"].map(lambda x: "{:,.2f}".format(x) if pd.notna(x) else "N/A")
        display_df["VALOR SUGERIDO"] = display_df["VALOR SUGERIDO"].map(lambda x: "{:,.2f}".format(x) if pd.notna(x) else "N/A")
        def _hl(row):
            return ['background-color: yellow' if str(row.get("EVALUACION")).strip().lower() == "bajo" else "" for _ in row]
        st.dataframe(display_df.style.apply(_hl, axis=1), use_container_width=True)
        return ctx

    # 2) Detect columns and construct SERVICE_U in sugeridos
    svc_col = find_col(sugeridos_df, ["Servicio Completo", "ServicioCompleto", "Servicio Completo (relacion servicio/especialidad)"])
    svc_alt = find_col(sugeridos_df, ["Servicio", "Servico"])
    spec_alt = find_col(sugeridos_df, ["Especialidad", "Especialidad REPS", "Especialidad"])
    min_col = find_col(sugeridos_df, ["Minimo", "Mínimo Recomendado", "Minimo Recomendado (por 100.000 hab.)"])
    umbral_col = find_col(sugeridos_df, ["Umbral Alto", "Umbral", "Umbral Alto (por 100.000 hab.)"])
    notes_col = find_col(sugeridos_df, ["Notas", "Fuente", "Observaciones", "Comentarios"])

    try:
        if svc_col and svc_col in sugeridos_df.columns:
            sugeridos_df['SERVICE_U'] = sugeridos_df[svc_col].astype(str).map(lambda x: normalize(x))
        elif svc_alt and svc_alt in sugeridos_df.columns:
            serv = sugeridos_df[svc_alt].astype(str).fillna("")
            spec = (sugeridos_df[spec_alt].astype(str).fillna("") if spec_alt and spec_alt in sugeridos_df.columns else "")
            if isinstance(spec, pd.Series):
                comb = serv + ((" - " + spec).where(spec.astype(bool), ""))
                sugeridos_df['SERVICE_U'] = comb.map(lambda x: normalize(x))
            else:
                sugeridos_df['SERVICE_U'] = serv.map(lambda x: normalize(x))
        else:
            sugeridos_df['SERVICE_U'] = sugeridos_df.index.astype(str).map(lambda x: normalize(str(x)))
    except Exception:
        sugeridos_df['SERVICE_U'] = sugeridos_df.index.astype(str).map(lambda x: normalize(str(x)))

    # parse numeric columns
    try:
        if min_col and min_col in sugeridos_df.columns:
            sugeridos_df['MIN_RECO'] = sugeridos_df[min_col].map(lambda x: _to_num(x))
        else:
            sugeridos_df['MIN_RECO'] = np.nan
    except Exception:
        sugeridos_df['MIN_RECO'] = np.nan

    try:
        if umbral_col and umbral_col in sugeridos_df.columns:
            sugeridos_df['UMBRAL_ALTO'] = sugeridos_df[umbral_col].map(lambda x: _to_num(x))
        else:
            sugeridos_df['UMBRAL_ALTO'] = np.nan
    except Exception:
        sugeridos_df['UMBRAL_ALTO'] = np.nan

    # fallback extraction from text when numeric parsing failed
    if sugeridos_df['MIN_RECO'].notna().sum() == 0:
        candidate_cols = [c for c in [min_col, notes_col, svc_col, svc_alt] if c and c in sugeridos_df.columns]
        for c in candidate_cols:
            sugeridos_df['MIN_RECO'] = sugeridos_df['MIN_RECO'].fillna(sugeridos_df[c].astype(str).map(lambda v: (float(re.search(r"[-+]?\d+[.,]?\d*", str(v)).group(0).replace(',', '.')) if re.search(r"[-+]?\d+[.,]?\d*", str(v)) else np.nan)))

    # 3) Apply existing user mappings first
    mappings_df = _load_mappings()
    map_dict = {}
    if not mappings_df.empty and 'combo' in mappings_df.columns and 'SERVICE_U' in mappings_df.columns:
        map_dict = dict(zip(mappings_df['combo'].astype(str), mappings_df['SERVICE_U'].astype(str)))

    display_col = 'SERVICIO | ESPECIALIDAD' if 'SERVICIO | ESPECIALIDAD' in servicios_df.columns else ('COMBO' if 'COMBO' in servicios_df.columns else servicios_df.columns[0])
    servicios_df[display_col] = servicios_df[display_col].astype(str)

    servicios_df['SUG_KEY_MATCH'] = None
    servicios_df['SUG_MATCH_METHOD'] = None

    for i, row in servicios_df.iterrows():
        combo = str(row[display_col])
        if combo in map_dict and pd.notna(map_dict[combo]) and map_dict[combo] != "":
            servicios_df.at[i, 'SUG_KEY_MATCH'] = str(map_dict[combo])
            servicios_df.at[i, 'SUG_MATCH_METHOD'] = "user-mapped"

    # 4) auto-matching: keys from sugeridos
    keys = sugeridos_df['SERVICE_U'].dropna().astype(str).unique().tolist()

    def _best_match_for(label: str, cutoff=0.55) -> Optional[str]:
        if not label or not keys:
            return None
        kn = normalize(str(label))
        if kn in keys:
            return kn
        for kk in keys:
            if kk and (kk in kn or kn in kk):
                return kk
        kn_tok = _norm_tokens(normalize, label)
        for kk in keys:
            kk_tok = _norm_tokens(normalize, kk)
            if kk_tok and (kk_tok in kn_tok or kn_tok in kk_tok):
                return kk
        cands = difflib.get_close_matches(kn_tok or kn, keys, n=3, cutoff=cutoff)
        return cands[0] if cands else None

    for i, row in servicios_df.iterrows():
        if pd.notna(row.get('SUG_KEY_MATCH')):
            continue
        combo = str(row[display_col])
        candidate = _best_match_for(combo, cutoff=0.55)
        if candidate:
            servicios_df.at[i, 'SUG_KEY_MATCH'] = candidate
            orig_norm = normalize(combo)
            if candidate == orig_norm:
                method = "exact"
            elif candidate in orig_norm or orig_norm in candidate:
                method = "contains"
            else:
                method = "fuzzy"
            servicios_df.at[i, 'SUG_MATCH_METHOD'] = method

    # 5) classification and suggested values
    map_min = dict(zip(sugeridos_df['SERVICE_U'].astype(str), sugeridos_df.get('MIN_RECO', pd.Series([np.nan]*len(sugeridos_df))).astype(float)))
    map_um = dict(zip(sugeridos_df['SERVICE_U'].astype(str), sugeridos_df.get('UMBRAL_ALTO', pd.Series([np.nan]*len(sugeridos_df))).astype(float)))

    servicios_df['INDICADOR_NUM'] = pd.to_numeric(servicios_df.get('INDICADOR_POR_ESCALA', servicios_df.get('INDICADOR_NUM', pd.Series([np.nan]*len(servicios_df)))), errors='coerce')

    def _classify(iv, k):
        try:
            if pd.isna(iv):
                return "N/A"
            if not k:
                return "No benchmark"
            rec_min = map_min.get(k, np.nan)
            rec_um = map_um.get(k, np.nan)
            ivf = float(iv)
            if pd.notna(rec_um) and ivf >= rec_um:
                return "Alto"
            if pd.notna(rec_min) and ivf >= rec_min:
                return "Normal"
            return "Bajo"
        except Exception:
            return "N/A"

    servicios_df['EVALUACIÓN (sugerido)'] = servicios_df.apply(lambda r: _classify(r.get('INDICADOR_NUM'), r.get('SUG_KEY_MATCH')), axis=1)

    def _get_valor_sug(k):
        if not k:
            return np.nan
        v = map_min.get(k)
        if pd.notna(v):
            return float(v)
        v2 = map_um.get(k)
        if pd.notna(v2):
            return float(v2)
        return np.nan

    servicios_df['VALOR SUGERIDO'] = servicios_df['SUG_KEY_MATCH'].map(lambda k: _get_valor_sug(k))

    desv = servicios_df.apply(lambda r: (np.nan, np.nan) if (pd.isna(r.get('VALOR SUGERIDO')) or pd.isna(r.get('INDICADOR_NUM')) or r.get('VALOR SUGERIDO')==0) else (r.get('INDICADOR_NUM')-r.get('VALOR SUGERIDO'), ((r.get('INDICADOR_NUM')-r.get('VALOR SUGERIDO'))/r.get('VALOR SUGERIDO'))*100), axis=1, result_type='expand')
    servicios_df['DIF ABS'] = desv.iloc[:,0]
    servicios_df['DESVIACIÓN (%)'] = desv.iloc[:,1]

    ctx.setdefault("outputs", {})["servicios_eval"] = servicios_df

    # 6) build final display dataframe with requested columns (keep numeric 'display' for calculations)
    display = pd.DataFrame()
    if 'SERVICIO | ESPECIALIDAD' in servicios_df.columns:
        display['SERVICIO | ESPECIALIDAD'] = servicios_df['SERVICIO | ESPECIALIDAD'].astype(str)
    else:
        display['SERVICIO | ESPECIALIDAD'] = servicios_df.get('COMBO', servicios_df.index.astype(str)).astype(str)

    display['SEDES'] = pd.to_numeric(servicios_df.get('SEDES_N', servicios_df.get('SEDES', pd.Series([0]*len(servicios_df)))), errors='coerce').fillna(0).astype(int)

    if 'TOTAL_OFERTA_NUM' in servicios_df.columns:
        display['OFERTA'] = pd.to_numeric(servicios_df['TOTAL_OFERTA_NUM'], errors='coerce').fillna(0)
    else:
        display['OFERTA'] = pd.to_numeric(servicios_df.get('TOTAL_OFERTA', 0), errors='coerce').fillna(0)

    if 'POBLACION_NUM' in servicios_df.columns:
        display['POBLACION'] = pd.to_numeric(servicios_df['POBLACION_NUM'], errors='coerce').fillna(0)
    else:
        display['POBLACION'] = pd.to_numeric(servicios_df.get('POBLACION', 0), errors='coerce').fillna(0)

    if 'INDICADOR_POR_ESCALA' in servicios_df.columns:
        display['OFERTA X 100.000'] = pd.to_numeric(servicios_df['INDICADOR_POR_ESCALA'], errors='coerce')
    else:
        display['OFERTA X 100.000'] = pd.to_numeric(servicios_df.get('INDICADOR_NUM', pd.Series([np.nan]*len(servicios_df))), errors='coerce')

    display['EVALUACION'] = servicios_df.get('EVALUACIÓN (sugerido)', servicios_df.get('EVALUACION', "No benchmark")).astype(str)
    display['VALOR SUGERIDO'] = pd.to_numeric(servicios_df.get('VALOR SUGERIDO', np.nan), errors='coerce')

    # ---- NEW: add CATEGORY before filtering ----
    def _category_of(text: str) -> str:
        try:
            return text.split("|")[0].strip().upper()
        except Exception:
            return str(text).strip().upper()
    display['CATEGORY'] = display['SERVICIO | ESPECIALIDAD'].map(_category_of)

    # Format display copy for UI
    display_formatted = display.copy()
    display_formatted['SEDES'] = display['SEDES'].map(lambda x: "{:,.0f}".format(x) if pd.notna(x) else "0")
    display_formatted['OFERTA'] = display['OFERTA'].map(lambda x: "{:,.0f}".format(x) if pd.notna(x) else "0")
    display_formatted['POBLACION'] = display['POBLACION'].map(lambda x: "{:,.0f}".format(x) if pd.notna(x) else "0")
    display_formatted['OFERTA X 100.000'] = display['OFERTA X 100.000'].map(lambda x: "{:,.2f}".format(x) if pd.notna(x) else "N/A")
    display_formatted['VALOR SUGERIDO'] = display['VALOR SUGERIDO'].map(lambda x: "{:,.2f}".format(x) if pd.notna(x) else "N/A")

    # highlight rows where EVALUACION == 'Bajo'
    def _highlight_low(row):
        return ['background-color: yellow' if str(row['EVALUACION']).strip().lower() == "bajo" else "" for _ in row]

    st.dataframe(display_formatted.style.apply(_highlight_low, axis=1), use_container_width=True)

    # 7) Bar chart for 'Bajo' cases and category filter
    bajos = display[display['EVALUACION'].str.strip().str.lower() == "bajo"].copy()

    if bajos.empty:
        st.info("No hay casos clasificados como 'Bajo' para mostrar en el gráfico.")
        return ctx

    categorias = sorted(display['CATEGORY'].dropna().unique().tolist())
    categorias_opts = ["TODOS"] + categorias
    selected_cat = st.selectbox("Filtrar por categoría para el gráfico", options=categorias_opts, index=0, key="block3_category_select")

    # filter bajos by category
    if selected_cat and selected_cat != "TODOS":
        bajos = bajos[bajos['CATEGORY'] == selected_cat]

    if bajos.empty:
        st.info("No hay casos 'Bajo' en la categoría seleccionada.")
        return ctx

    escala = int(ctx.get('display_options', {}).get('escala', 100000))
    # desired total (units) = VALOR SUGERIDO (per escala) * POBLACION / escala
    bajos['DESIRED_TOTAL'] = (bajos['VALOR SUGERIDO'].fillna(0.0) * bajos['POBLACION'].fillna(0.0)) / escala
    bajos['INCREASE_NEEDED'] = (bajos['DESIRED_TOTAL'] - bajos['OFERTA']).fillna(0.0).apply(lambda x: max(0, x))
    bajos['INCREASE_NEEDED_INT'] = bajos['INCREASE_NEEDED'].round(0).astype(int)

    agg = bajos.groupby('SERVICIO | ESPECIALIDAD', as_index=False)['INCREASE_NEEDED_INT'].sum().rename(columns={'INCREASE_NEEDED_INT':'INCREASE_NEEDED'})
    if agg.empty:
        st.info("No hay aumentos requeridos calculables para los casos 'Bajo'.")
        return ctx
    agg = agg.sort_values('INCREASE_NEEDED', ascending=False).reset_index(drop=True)

    try:
        fig = px.bar(agg, x='INCREASE_NEEDED', y='SERVICIO | ESPECIALIDAD', orientation='h',
                     labels={'INCREASE_NEEDED': 'Unidades a adquirir', 'SERVICIO | ESPECIALIDAD': 'Servicio | Especialidad'},
                     text='INCREASE_NEEDED',
                     height=400 + 20 * min(len(agg), 20))
        fig.update_traces(texttemplate='%{text:,}', textposition='outside')
        fig.update_layout(yaxis={'automargin': True}, bargap=0.2)
        st.subheader("Brecha estimada (solo casos 'Bajo') — unidades a adquirir")
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"No fue posible generar el gráfico interactivo: {e}")

    # Summary sentence for the top required item
    top = agg.iloc[0]
    top_service = top['SERVICIO | ESPECIALIDAD']
    top_qty = int(top['INCREASE_NEEDED'])
    cat_prefix = selected_cat if (selected_cat and selected_cat != "TODOS") else _category_of(top_service)
    unit_map = {
        "CAMAS": "camas",
        "CAMILLAS": "camillas",
        "SILLAS": "sillas",
        "SALAS": "salas",
        "AMBULANCIAS": "ambulancias",
        "UNIDAD MOVIL": "unidades móviles",
        "UNIDAD MOVIL ": "unidades móviles",
    }
    unit = unit_map.get(cat_prefix.upper(), "unidades")
    filters = ctx.get('filters', {})
    location = filters.get('Municipio') or filters.get('Departamento') or "la zona seleccionada"
    top_qty_fmt = "{:,}".format(top_qty)
    st.markdown(f"**Resumen:** Hay que invertir para adquirir aproximadamente **{top_qty_fmt} {unit}** para *{location}* en **{top_service}**.")

    return ctx
"""Sidebar filters component.

Behavior:
- For each select we render an option 'TODAS' as the first option.
- If user selects 'TODAS' (the default), the function returns None meaning "no filter".
- The filters function returns a dict with selections.
"""
import streamlit as st

def select_with_todas(label, options, key=None, multiselect=False):
    opts = ["TODAS"] + sorted(options)
    if multiselect:
        sel = st.multiselect(label, opts, default=["TODAS"], key=key)
        if not sel or "TODAS" in sel:
            return None
        return sel
    else:
        sel = st.selectbox(label, opts, index=0, key=key)
        return None if sel == "TODAS" else sel

def sidebar_filters(df=None):
    """
    If df provided, we prefill caches into session_state for options.
    Returns dict of filter selections.
    """
    st.sidebar.header("Filtros Generales")
    # populate caches if df passed
    if df is not None:
        st.session_state.setdefault("_departamentos_cache", sorted(df['Departamento'].dropna().unique()) if 'Departamento' in df.columns else [])
        st.session_state.setdefault("_municipios_cache", sorted(df['Municipio'].dropna().unique()) if 'Municipio' in df.columns else [])
        st.session_state.setdefault("_naturalezas_cache", sorted(df['naturaleza'].dropna().unique()) if 'naturaleza' in df.columns else [])
        st.session_state.setdefault("_niveles_cache", sorted(df['num nivel atencion'].dropna().unique()) if 'num nivel atencion' in df.columns else [])

    departamento = select_with_todas("Departamento", st.session_state.get("_departamentos_cache", []), key="f_depto")
    municipio = select_with_todas("Municipio", st.session_state.get("_municipios_cache", []), key="f_mpio", multiselect=True)
    naturaleza = select_with_todas("Naturaleza Jurídica", st.session_state.get("_naturalezas_cache", []), key="f_naturaleza", multiselect=True)
    nivel = select_with_todas("Nivel de Atención", st.session_state.get("_niveles_cache", []), key="f_nivel", multiselect=True)

    factor_operativo = st.sidebar.slider("Factor operativo", 0.5, 2.0, 1.0, 0.1)

    return {
        "Departamento": departamento,
        "Municipio": municipio,
        "Naturaleza": naturaleza,
        "Nivel": nivel,
        "factor_operativo": factor_operativo
    }

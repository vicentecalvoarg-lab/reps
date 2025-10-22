# app/pagina/master_ips.py
"""
Wrapper page for MASTER IPS.

This module is the page entrypoint used by main.py. It provides the run(filters, df_filtered, df_all)
function that the main dispatcher calls. It delegates the heavy work to app.pagina.master_ips_impl.run(...)
and then presents final UI/diagnostics, persists the context in session_state and exposes the
Excel export UI (if master_ips_export is available).
"""
from typing import Dict, Any, Optional
import importlib
import traceback

import streamlit as st
import pandas as pd

# Keep a short user-visible title for the page
st.set_page_config(page_title="MASTER IPS", layout="wide")

def _safe_list_outputs(ctx: Dict[str, Any]) -> Dict[str, int]:
    """Return a mapping output_key -> number of rows (or 0 if non-DataFrame)."""
    outs = {}
    for k, v in (ctx.get("outputs") or {}).items():
        try:
            if isinstance(v, pd.DataFrame):
                outs[k] = int(len(v))
            else:
                outs[k] = 1
        except Exception:
            outs[k] = 0
    return outs

def run(filters: dict, df_filtered: Optional[pd.DataFrame], df_all: Optional[pd.DataFrame]):
    """
    Entrypoint called by main.py.
    Signature preserved: run(filters, df_filtered, df_all)
    """
    st.title("MASTER IPS — Orquestador y ejecución completa")
    st.write("Este módulo ejecuta todos los sub-bloques del orquestador MASTER IPS y prepara los outputs para export/inspección.")

    # Import the implementation module that performs the block execution.
    try:
        impl = importlib.import_module("app.pagina.master_ips_impl")
    except Exception as e:
        st.error("No fue posible importar app.pagina.master_ips_impl. Revisa la traza:")
        st.exception(traceback.format_exc())
        return

    # Provide a visible button to (re)ejecutar todo — useful for interactive debugging.
    if "master_ips_last_run" not in st.session_state:
        st.session_state["master_ips_last_run"] = None

    col_run, col_info = st.columns([1, 3])
    with col_run:
        run_button = st.button("Ejecutar MASTER IPS (procesamiento 100%)", key="master_ips_run_button")
    with col_info:
        last = st.session_state.get("master_ips_last_run")
        if last:
            st.markdown(f"Última ejecución: {last}")

    # If the page was called from main.py automatically, run once automatically (to match previous behaviour).
    auto_run = True
    # If user explicitly presses the button, force a run.
    if run_button:
        auto_run = True

    if auto_run:
        st.info("Iniciando ejecución del orquestador. Esto ejecuta los bloques 01→05 en orden.")
        try:
            # Call the implementation. It must return the context dict (ctx).
            ctx = impl.run(filters, df_filtered, df_all)
            # If module returned None, attempt to retrieve ctx from impl (some versions may store state)
            if ctx is None:
                # fallback — try to get ctx from st.session_state if impl stored it there
                ctx = st.session_state.get("master_ips_ctx", {})
            if not isinstance(ctx, dict):
                st.warning("El orquestador no retornó un contexto válido (ctx). Se creará uno vacío.")
                ctx = {"outputs": {}}

            # Save context in session_state for downstream inspection
            st.session_state["master_ips_ctx"] = ctx
            st.session_state["master_ips_last_run"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

            # Summarize outputs
            outs_summary = _safe_list_outputs(ctx)
            if outs_summary:
                st.success("Procesamiento completado. Outputs generados:")
                for k, cnt in outs_summary.items():
                    st.write(f"- {k}: {cnt:,} filas (tipo: {'DataFrame' if isinstance(ctx['outputs'][k], pd.DataFrame) else type(ctx['outputs'][k]).__name__})")
            else:
                st.warning("Procesamiento finalizó pero no se detectaron salidas en ctx['outputs'].")

            # If specific expected outputs exist, show quick previews
            with st.expander("Previews de outputs (primeras 10 filas por hoja)"):
                for k, v in (ctx.get("outputs") or {}).items():
                    try:
                        if isinstance(v, pd.DataFrame):
                            st.markdown(f"**{k}** — {len(v):,} filas")
                            st.dataframe(v.head(10), use_container_width=True)
                        else:
                            st.markdown(f"**{k}** — (no-DataFrame): {str(v)[:200]}")
                    except Exception:
                        st.write(f"Imposible mostrar preview de {k}")

            # Offer export button if export module available
            try:
                export_mod = importlib.import_module("app.pagina.master_ips_export")
                if hasattr(export_mod, "show_export_button"):
                    st.markdown("---")
                    st.info("Generar export (Excel) con todos los outputs disponibles")
                    export_mod.show_export_button(ctx)
                else:
                    st.info("Módulo de export (master_ips_export) presente pero no expone show_export_button().")
            except Exception:
                st.info("Módulo master_ips_export no disponible — el export a Excel no está habilitado.")

            # Final confirmation
            st.success("MASTER IPS procesado 100% — revisa las secciones anteriores y descarga el Excel si lo deseas.")
        except Exception as e:
            st.error("Ocurrió un error durante la ejecución del orquestador MASTER IPS. Revisa la traza:")
            st.exception(traceback.format_exc())
            return

    # Provide a small utilities block: inspect ctx, clear ctx
    st.markdown("---")
    col_dbg_1, col_dbg_2 = st.columns([1,1])
    with col_dbg_1:
        if st.button("Mostrar ctx en session_state", key="master_ips_show_ctx"):
            st.json(st.session_state.get("master_ips_ctx", {}))
    with col_dbg_2:
        if st.button("Borrar ctx guardado", key="master_ips_clear_ctx"):
            st.session_state.pop("master_ips_ctx", None)
            st.success("Contexto guardado eliminado.")

    return  # page run ends here

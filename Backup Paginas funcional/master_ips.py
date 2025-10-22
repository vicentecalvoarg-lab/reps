# wrapper seguro para evitar que errores de import en tiempo de carga rompan el dashboard
def run(filters, df_filtered, df_all):
    try:
        # importamos la implementación pesada solo cuando se necesita
        from . import master_ips_impl as impl
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            import streamlit as st
            st.error("Error importando la implementación de master_ips:\n" + str(e))
            st.text(tb)
            return
        except Exception:
            raise RuntimeError("Error importando master_ips_impl") from e
    # llamar la implementación
    return impl.run(filters, df_filtered, df_all)
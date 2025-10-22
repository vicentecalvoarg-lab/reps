"""
Generate full project scaffold under C:/REPS for the modular Streamlit dashboard.

Usage:
    python generate_project_files.py

Behavior:
- Creates the folder structure under C:/REPS
- Writes all module files, README, requirements.txt, and __init__.py files
- By default overwrites existing files (change OVERWRITE = False to prevent)

After running:
- Put your dataset at C:/REPS/data/output_data.parquet (or output_data.csv)
- Install requirements: pip install -r C:/REPS/requirements.txt
- Run the app: streamlit run C:/REPS/app/main.py

Note: The generated files are the same modules we discussed (data loader, utils,
standards, components, pages, main, config, README). Review the files and adapt
column-name detection if your dataset uses different names.
"""
from pathlib import Path
import os
import textwrap

BASE = Path("C:/REPS")
OVERWRITE = True  # set to False to avoid overwriting existing files

# Files to create: mapping relative path -> content
files = {
    "create_project_structure.py": textwrap.dedent("""\
        \"\"\"Utility to create the folder structure under C:/REPS and example data folder.
        Run this once on Windows to create directories:
            python create_project_structure.py

        This script only creates directories. Place your data files (parquet / csv) as described in README.md.
        \"\"\"
        import os
        from pathlib import Path

        BASE = Path("C:/REPS")

        dirs = [
            BASE,
            BASE / "data",
            BASE / "app",
            BASE / "app" / "components",
            BASE / "app" / "pages",
            BASE / "app" / "tests",
        ]

        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            print(f"Ensured directory: {d}")

        print("\\nDone. Now copy the files provided (the app/ tree) into C:/REPS or run Streamlit from the project root that contains the 'app' package.")
        print("Put your data file at: C:/REPS/data/output_data.parquet (or output_data.csv). See README.md for details.")
        """),
    "app/__init__.py": "",
    "app/components/__init__.py": "",
    "app/pages/__init__.py": "",
    "app/config.py": textwrap.dedent("""\
        \"\"\"Configuration for the dashboard.

        By default DATA_DIR is C:/REPS/data but can be overridden setting env var REPS_DATA_DIR.
        \"\"\"
        from pathlib import Path
        import os

        DATA_DIR = Path(os.environ.get("REPS_DATA_DIR", "C:/REPS/data"))
        # default filename we expect
        DEFAULT_PARQUET = DATA_DIR / "output_data.parquet"
        DEFAULT_CSV = DATA_DIR / "output_data.csv"
        """),
    "app/data.py": textwrap.dedent("""\
        \"\"\"Data loading and basic helpers (cached).\"\"\"
        from pathlib import Path
        import pandas as pd
        import streamlit as st
        import re
        from app import config

        @st.cache_data(show_spinner=False)
        def load_data(path: str | None = None):
            \"\"\"
            Load dataset. If path None, try DEFAULT_PARQUET then DEFAULT_CSV.
            Returns a DataFrame.
            \"\"\"
            p = None
            if path:
                p = Path(path)
            else:
                if config.DEFAULT_PARQUET.exists():
                    p = config.DEFAULT_PARQUET
                elif config.DEFAULT_CSV.exists():
                    p = config.DEFAULT_CSV
            if p is None or not p.exists():
                raise FileNotFoundError(f\"No data file found. Put your dataset at {config.DEFAULT_PARQUET} or {config.DEFAULT_CSV} or pass path to load_data().\")
            if p.suffix.lower() in [\".parquet\"]:
                df = pd.read_parquet(p)
            else:
                df = pd.read_csv(p)
            # Normalize numeric capacity installed
            if 'num cantidad capacidad instalada' in df.columns:
                df['num cantidad capacidad instalada'] = pd.to_numeric(df['num cantidad capacidad instalada'], errors='coerce').fillna(0)
            # Some minimal date handling
            if 'Fecha Corte' in df.columns:
                df['Fecha Corte'] = pd.to_datetime(df['Fecha Corte'], errors='coerce')
            return df

        def explode_nits_regex(df, nit_col='nit IPS', token_min_length=6):
            \"\"\"
            Extract possible NIT tokens from a messy nit column.
            Returns DataFrame with columns: _orig_index, nit_token, nit_normalized
            \"\"\"
            df = df.copy()
            df['_orig_index'] = df.index
            if nit_col not in df.columns:
                return pd.DataFrame(columns=['_orig_index', 'nit_token', 'nit_normalized'])
            tokens_rows = []
            pattern = re.compile(r'[\\d\\.,\\-\\s]{' + str(token_min_length) + r',}')
            for idx, val in df[nit_col].fillna('').astype(str).items():
                text = val.strip()
                if text == '':
                    continue
                found = pattern.findall(text)
                if not found:
                    if len(re.sub(r'\\D', '', text)) >= 3:
                        found = [text]
                for tok in found:
                    tok_clean = tok.strip()
                    nit_norm = re.sub(r'\\D', '', tok_clean)
                    if nit_norm == "":
                        continue
                    tokens_rows.append({'_orig_index': idx, 'nit_token': tok_clean, 'nit_normalized': nit_norm})
            if not tokens_rows:
                return pd.DataFrame(columns=['_orig_index', 'nit_token', 'nit_normalized'])
            return pd.DataFrame(tokens_rows)
        """),
    "app/utils.py": textwrap.dedent("""\
        \"\"\"General small utilities used across modules.\"\"\"
        import re
        import hashlib

        def format_number(x):
            try:
                return f\"{int(x):,}\"
            except Exception:
                try:
                    return f\"{float(x):,.0f}\"
                except Exception:
                    return x

        def normalize_nit(val):
            if val is None:
                return \"\"
            return re.sub(r'\\D', '', str(val))

        def hash_seed(*args) -> int:
            key = \"|\".join([str(a) for a in args])
            h = hashlib.md5(key.encode(\"utf-8\")).hexdigest()
            return int(h[:8], 16)
        """),
    "app/standards.py": textwrap.dedent("""\
        \"\"\"Service standards mapping and lookup.
        Keep this file focused on the service_standard_map and the matching logic.
        \"\"\"
        service_standard_map = [
            (["sala de procedimientos", "salas de procedimientos", "procedimientos"], "Salas", 7.5),
            (["sala quirófano", "salas quirófano", "salas quirófanos", "sala quirófanos", "quirófanos", "sala de cirugía", "sala cirugia", "sala de cirugia"], "Salas/Quirófanos", 2.8),
            (["salas de traumatología", "traumatología"], "Salas", 5.0),
            (["salas de quimioterapia", "quimioterapia", "sillas de quimioterapia"], "Salas", 3.0),
            (["salas de radioterapia", "radioterapia"], "Salas", 12.5),
            (["sillas de hemodiálisis", "hemodiálisis", "sillas hemodiálisis", "salas de hemodiálisis"], "Máquinas", 3.5),
            (["salas spa", "spa", "spa básico adultos", "spa básico pediátricos"], "Camas", 0.18),
            (["camas de pediatría", "camas pediatría", "camas pediátricos", "pediatría", "pediátrica"], "Camas", 0.18),
            (["camas spa pediátricas", "spa pediátricas"], "Camas", 0.18),
            (["camas intermedia pediátrica", "intermedia pediátrica"], "Camas", 0.18),
            (["camas cuna intensiva pediátrica", "u ci pediátrica"], "Cunas", 0.18),
            (["adultos del parto", "parto", "obstetricia", "adultos"], "Camas", 0.18),
            (["consultorios partos", "partos externos"], "Consultorios", 16.0),
            (["camillas de observación pediátrica", "camillas observación pediátrica"], "Camillas", 0.85),
            (["camillas de observación adultos", "observación adultos", "observación adultos hombres", "observación adultos mujeres"], "Camillas", 0.85),
            (["consultorios urgencia", "consultorios urgencia adultos", "urgencia", "urgencias"], "Consultorios", 75.0),
            (["consulta externa"], "Consultorios", 20.0),
            (["unidad móvil pediátrica", "unidad móvil"], "Unidad Móvil", 3.0),
            (["ambulancias", "básica", "medicalizada"], "Ambulancias", 2.0),
            (["camas incubadora intensiva neonatal", "incubadora intensiva neonatal"], "Camas/Incubadoras", 0.18),
            (["camas cuna básica neonatal", "cuna básica neonatal"], "Cunas", 0.18),
            (["camas cuna intermedia neonatal", "cuna intermedia neonatal"], "Cunas", 0.18),
            (["salud mental adulto", "salud mental pediátrico"], "Camas", 0.10),
            (["tpr"], "Camas", 0.18),
            (["paciente crónico sin ventilador"], "Camas", 0.10),
            (["otras patologías"], "Camillas", 0.85),
        ]

        def find_standard_for_service(service_text):
            if not isinstance(service_text, str):
                return None
            s = service_text.lower()
            for keys, unit_type, daily_per_unit in service_standard_map:
                for k in keys:
                    if k in s:
                        return {\"unit_type\": unit_type, \"daily_per_unit\": daily_per_unit, \"matched_key\": k}
            return None
        """),
    "app/components/filters.py": textwrap.dedent("""\
        \"\"\"Sidebar filters component.

        Behavior:
        - For each select we render an option 'TODAS' as the first option.
        - If user selects 'TODAS' (the default), the function returns None meaning "no filter".
        - The filters function returns a dict with selections.
        \"\"\"
        import streamlit as st

        def select_with_todas(label, options, key=None, multiselect=False):
            opts = [\"TODAS\"] + sorted(options)
            if multiselect:
                sel = st.multiselect(label, opts, default=[\"TODAS\"], key=key)
                if not sel or \"TODAS\" in sel:
                    return None
                return sel
            else:
                sel = st.selectbox(label, opts, index=0, key=key)
                return None if sel == \"TODAS\" else sel

        def sidebar_filters(df=None):
            \"\"\"
            If df provided, we prefill caches into session_state for options.
            Returns dict of filter selections.
            \"\"\"
            st.sidebar.header(\"Filtros Generales\")
            # populate caches if df passed
            if df is not None:
                st.session_state.setdefault(\"_departamentos_cache\", sorted(df['Departamento'].dropna().unique()) if 'Departamento' in df.columns else [])
                st.session_state.setdefault(\"_municipios_cache\", sorted(df['Municipio'].dropna().unique()) if 'Municipio' in df.columns else [])
                st.session_state.setdefault(\"_naturalezas_cache\", sorted(df['naturaleza'].dropna().unique()) if 'naturaleza' in df.columns else [])
                st.session_state.setdefault(\"_niveles_cache\", sorted(df['num nivel atencion'].dropna().unique()) if 'num nivel atencion' in df.columns else [])

            departamento = select_with_todas(\"Departamento\", st.session_state.get(\"_departamentos_cache\", []), key=\"f_depto\")
            municipio = select_with_todas(\"Municipio\", st.session_state.get(\"_municipios_cache\", []), key=\"f_mpio\", multiselect=True)
            naturaleza = select_with_todas(\"Naturaleza Jurídica\", st.session_state.get(\"_naturalezas_cache\", []), key=\"f_naturaleza\", multiselect=True)
            nivel = select_with_todas(\"Nivel de Atención\", st.session_state.get(\"_niveles_cache\", []), key=\"f_nivel\", multiselect=True)

            factor_operativo = st.sidebar.slider(\"Factor operativo\", 0.5, 2.0, 1.0, 0.1)

            return {
                \"Departamento\": departamento,
                \"Municipio\": municipio,
                \"Naturaleza\": naturaleza,
                \"Nivel\": nivel,
                \"factor_operativo\": factor_operativo
            }
        """),
    "app/components/tables.py": textwrap.dedent("""\
        \"\"\"Helpers to display tables and Export to Excel.\"\"\"
        import io
        import pandas as pd
        import streamlit as st

        def download_excel(dfs: dict, filename=\"report.xlsx\"):
            \"\"\"
            dfs: mapping sheet_name -> DataFrame
            returns a st.download_button
            \"\"\"
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                for sheet, df in dfs.items():
                    try:
                        df.to_excel(writer, sheet_name=sheet[:31], index=False)
                    except Exception:
                        # fallback: convert to string
                        pd.DataFrame(df).to_excel(writer, sheet_name=sheet[:31], index=False)
            data = buf.getvalue()
            return st.download_button(\"⬇️ Descargar simulación (Excel)\", data=data, file_name=filename, mime=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\")
        """),
    "app/pages/analysis_ips.py": textwrap.dedent("""\
        \"\"\"Analysis page implementing the simulator (migrated from monolith).

        Expose run(filters) function.
        \"\"\"
        import streamlit as st
        import pandas as pd
        import numpy as np
        from app.data import load_data, explode_nits_regex
        from app.components import filters as filters_comp
        from app.components import tables as tables_comp
        from app.utils import normalize_nit, hash_seed, format_number
        from app.standards import find_standard_for_service

        def run(filters: dict):
            st.header(\"Análisis IPS — Simulación (migrado)\")
            # Load data
            try:
                df = load_data()
            except Exception as e:
                st.error(f\"No se pudo cargar la base de datos: {e}\")
                st.stop()

            # initialize caches for sidebar selects
            filters_comp.sidebar_filters(df=df)

            # Apply high-level filters from sidebar (None means no filter)
            df_filtered = df.copy()
            if filters.get(\"Departamento\"):
                vals = filters[\"Departamento\"]
                if isinstance(vals, list):
                    df_filtered = df_filtered[df_filtered['Departamento'].isin(vals)]
                else:
                    df_filtered = df_filtered[df_filtered['Departamento'] == vals]
            if filters.get(\"Municipio\"):
                vals = filters[\"Municipio\"]
                if isinstance(vals, list):
                    df_filtered = df_filtered[df_filtered['Municipio'].isin(vals)]
                else:
                    df_filtered = df_filtered[df_filtered['Municipio'] == vals]
            if filters.get(\"Naturaleza\"):
                vals = filters[\"Naturaleza\"]
                if isinstance(vals, list):
                    df_filtered = df_filtered[df_filtered['naturaleza'].isin(vals)]
                else:
                    df_filtered = df_filtered[df_filtered['naturaleza'] == vals]
            if filters.get(\"Nivel\"):
                vals = filters[\"Nivel\"]
                if isinstance(vals, list):
                    df_filtered = df_filtered[df_filtered['num nivel atencion'].isin(vals)]
                else:
                    df_filtered = df_filtered[df_filtered['num nivel atencion'] == vals]

            st.write(f\"Filas luego de filtros: {len(df_filtered):,}\")

            # Prepare NIT list for selection (explode if needed)
            exploded = explode_nits_regex(df_filtered, 'nit IPS')
            nits = sorted(exploded['nit_token'].dropna().unique()) if not exploded.empty else []
            nit_select = st.selectbox(\"Selecciona NIT (o deja vacío)\", [\"\"] + nits, index=0)
            nit_input = st.text_input(\"O ingresa NIT manualmente (sin dígito verificador)\")
            nit_to_search = nit_input.strip() if nit_input.strip() else (nit_select.strip() if nit_select else \"\")
            if not nit_to_search:
                st.info(\"Selecciona o ingresa un NIT para ver la radiografía y simulación.\")
                return

            nit_norm = normalize_nit(nit_to_search)
            exploded_all = explode_nits_regex(df, 'nit IPS')
            matches = exploded_all[exploded_all['nit_normalized'] == nit_norm] if not exploded_all.empty else pd.DataFrame()
            if matches.empty:
                st.error(f\"No se encontró el NIT {nit_to_search}\")
                return
            idxs = matches['_orig_index'].unique().tolist()
            ips_rows = df.loc[idxs].reset_index(drop=True)

            # Build sede_id as codigo_sede + '|' + numero_sede when available
            codigo_sede_col = next((c for c in ['Código sede','Codigo sede','codigo sede','codigo_sede','Cod. sede','Codigo Sede'] if c in ips_rows.columns), None)
            numero_sede_col = next((c for c in ['Número sede','Numero sede','numero sede','num sede','numero_sede','nro sede'] if c in ips_rows.columns), None)
            nombre_sede_col = next((c for c in ['nom sede IPS','nom sede ips','Nom sede IPS','nom_sede_ips','Nombre sede','nombre_sede','Nombre de la sede'] if c in ips_rows.columns), None)

            def build_sede_id(row):
                parts = []
                if codigo_sede_col and pd.notna(row.get(codigo_sede_col)):
                    parts.append(str(row.get(codigo_sede_col)).strip())
                if numero_sede_col and pd.notna(row.get(numero_sede_col)):
                    parts.append(str(row.get(numero_sede_col)).strip())
                if parts:
                    return \"|\".join(parts)
                if codigo_sede_col and pd.notna(row.get(codigo_sede_col)):
                    return str(row.get(codigo_sede_col)).strip()
                if nombre_sede_col and pd.notna(row.get(nombre_sede_col)):
                    return str(row.get(nombre_sede_col)).strip()
                return \"sede_unknown\"
            ips_rows = ips_rows.copy()
            ips_rows['sede_id'] = ips_rows.apply(build_sede_id, axis=1)

            # Build unique sedes table
            cols_for_sede = []
            if codigo_sede_col: cols_for_sede.append(codigo_sede_col)
            if numero_sede_col: cols_for_sede.append(numero_sede_col)
            if nombre_sede_col: cols_for_sede.append(nombre_sede_col)
            if 'Departamento' in ips_rows.columns: cols_for_sede.append('Departamento')
            if 'Municipio' in ips_rows.columns: cols_for_sede.append('Municipio')
            if 'num nivel atencion' in ips_rows.columns: cols_for_sede.append('num nivel atencion')
            sede_unicas = ips_rows[cols_for_sede + ['sede_id']].drop_duplicates(subset=['sede_id']).reset_index(drop=True)

            display_map = {}
            if 'num nivel atencion' in ips_rows.columns:
                display_map['Nivel'] = 'num nivel atencion'
                sede_unicas = sede_unicas.rename(columns={'num nivel atencion': 'Nivel'})
            if 'Departamento' in sede_unicas.columns:
                display_map['Departamento'] = 'Departamento'
            if 'Municipio' in sede_unicas.columns:
                display_map['Municipio'] = 'Municipio'
            if nombre_sede_col:
                sede_unicas = sede_unicas.rename(columns={nombre_sede_col: 'Nombre sede'})
            if codigo_sede_col:
                sede_unicas = sede_unicas.rename(columns={codigo_sede_col: 'codigo_sede'})
            if numero_sede_col:
                sede_unicas = sede_unicas.rename(columns={numero_sede_col: 'numero_sede'})

            st.subheader(\"Sedes únicas del NIT\")
            if sede_unicas.empty:
                st.info(\"No se encontraron sedes.\")
            else:
                # show a cleaned view
                cols_show = [c for c in ['codigo_sede','numero_sede','Nombre sede','Departamento','Municipio','Nivel','sede_id'] if c in sede_unicas.columns]
                st.dataframe(sede_unicas[cols_show], use_container_width=True)

                # Summary by complexity level (Cantidad IPS counted as unique codigo+numero)
                nivel_col = 'Nivel' if 'Nivel' in sede_unicas.columns else None
                servicio_col = next((c for c in ['nom descripcion capacidad','nom_descripcion_capacidad','nom descripcion','descripcion servicio','descripcion','Servicio','servicio'] if c in ips_rows.columns), None)

                if nivel_col:
                    niveles = []
                    # iterate levels present in sede_unicas (preferred) else ips_rows
                    levels_values = sorted(sede_unicas[nivel_col].dropna().unique().tolist())
                    for lvl in levels_values:
                        mask_lvl = sede_unicas[nivel_col] == lvl
                        # count unique codigo_sede+numero_sede combos
                        if 'codigo_sede' in sede_unicas.columns and 'numero_sede' in sede_unicas.columns:
                            combos = sede_unicas.loc[mask_lvl, ['codigo_sede','numero_sede']].fillna(\"\").astype(str)
                            combos = combos.apply(lambda x: (x.iloc[0].strip() + \"|\" + x.iloc[1].strip()).strip(\"|\"), axis=1)
                            combos = combos[combos != \"\"]
                            qty_ips = int(combos.nunique())
                        else:
                            # fallback to unique sede_id
                            qty_ips = int(sede_unicas.loc[mask_lvl, 'sede_id'].nunique())
                        # services in ips_rows for that level
                        if servicio_col and servicio_col in ips_rows.columns:
                            # match level entries in ips_rows
                            if 'num nivel atencion' in ips_rows.columns:
                                qty_services = int(ips_rows.loc[ips_rows['num nivel atencion'] == lvl, servicio_col].dropna().astype(str).nunique())
                            else:
                                qty_services = int(ips_rows.loc[ips_rows['sede_id'].isin(sede_unicas.loc[mask_lvl,'sede_id']), servicio_col].dropna().astype(str).nunique())
                        else:
                            qty_services = 0
                        niveles.append({'Nivel de complejidad': lvl, 'Cantidad de IPS': qty_ips, 'Cantidad de servicios ofrecidos': qty_services})
                    resumen_nivel_df = pd.DataFrame(niveles)
                    st.subheader(\"Resumen por Nivel de complejidad\")
                    st.dataframe(resumen_nivel_df, use_container_width=True)
                else:
                    st.info(\"No hay columna de Nivel para hacer resumen por nivel.\")

            # Continue with Sedes por Servicio and simulation (migrated logic)
            st.subheader(\"Sedes por Servicio\")
            servicio_used = servicio_col
            if servicio_used:
                servicios_counts = ips_rows.groupby(servicio_used).size().reset_index(name='Cantidad')
                servicios_counts = servicios_counts.rename(columns={servicio_used:'Descripción del servicio'}).sort_values('Cantidad', ascending=False).reset_index(drop=True)
                st.dataframe(servicios_counts, use_container_width=True)
                servicio_values = servicios_counts['Descripción del servicio'].dropna().astype(str).tolist()
            else:
                st.info(\"No hay columna de servicio.\")
                servicio_values = []

            servicio_seleccionado = st.multiselect(\"Selecciona servicio(s):\", options=sorted(set(servicio_values)), default=None)

            # Build tabla_sedes_servicio (same logic as before but modular)
            tabla_sedes_servicio = pd.DataFrame()
            if servicio_seleccionado and servicio_used:
                mask = pd.Series(False, index=ips_rows.index)
                for sv in servicio_seleccionado:
                    mask = mask | ips_rows[servicio_used].astype(str).str.contains(sv, case=False, na=False)
                ips_servicio = ips_rows[mask].copy().reset_index(drop=True)

                # prepare select columns
                select_cols = ['sede_id']
                if codigo_sede_col and codigo_sede_col in ips_servicio.columns: select_cols.append(codigo_sede_col)
                if numero_sede_col and numero_sede_col in ips_servicio.columns: select_cols.append(numero_sede_col)
                if nombre_sede_col and nombre_sede_col in ips_servicio.columns: select_cols.append(nombre_sede_col)
                if 'Departamento' in ips_servicio.columns: select_cols.append('Departamento')
                if 'Municipio' in ips_servicio.columns: select_cols.append('Municipio')
                if 'num nivel atencion' in ips_servicio.columns: select_cols.append('num nivel atencion')
                if servicio_used in ips_servicio.columns: select_cols.append(servicio_used)
                tabla_sedes_servicio = ips_servicio.loc[:, select_cols].rename(columns={servicio_used:'Descripción del servicio'})

                # units_map priority
                units_map = {}
                if 'num cantidad capacidad instalada' in ips_rows.columns:
                    try:
                        units_series = ips_rows.groupby(['sede_id', servicio_used])['num cantidad capacidad instalada'].sum()
                        units_map = {(str(k[0]), str(k[1])): int(v) for k, v in units_series.items()}
                    except Exception:
                        units_map = {}

                counts_map = {}
                try:
                    counts_series = ips_rows.groupby(['sede_id', servicio_used]).size()
                    counts_map = {(str(k[0]), str(k[1])): int(v) for k, v in counts_series.items()}
                except Exception:
                    counts_map = {}

                def get_qty(row):
                    key = (str(row.get('sede_id','')), str(row.get('Descripción del servicio','')))
                    if units_map.get(key, 0) > 0:
                        return units_map.get(key, 0)
                    return counts_map.get(key, 0)

                tabla_sedes_servicio['Cantidad del servicio'] = tabla_sedes_servicio.apply(get_qty, axis=1).astype(int)

                # expected_daily base using standards
                expected_daily_list = []
                matched_list = []
                debug_list = []
                for _, r in tabla_sedes_servicio.reset_index(drop=True).iterrows():
                    svc_text = str(r.get('Descripción del servicio',''))
                    std = find_standard_for_service(svc_text)
                    key = (str(r.get('sede_id','')), svc_text)
                    units = units_map.get(key, 0)
                    if units == 0:
                        units = int(r.get('Cantidad del servicio', 0))
                    if std is not None and units > 0:
                        expected_daily = round(units * float(std['daily_per_unit']), 1)
                        expected_daily_list.append(expected_daily)
                        matched_list.append(std['matched_key'])
                        debug_list.append(f\"Matched: {std['matched_key']}\")
                    else:
                        base_count = int(r.get('Cantidad del servicio', 0))
                        if base_count == 0:
                            base_count = 1
                        s_lower = svc_text.lower()
                        if any(k in s_lower for k in ['camas','camillas','cuna','incubadora']):
                            scale = 0.18
                        elif any(k in s_lower for k in ['sala','quirófano','quirofano']):
                            scale = 5.0
                        else:
                            scale = 10.0
                        expected_daily_list.append(round(base_count * scale, 1))
                        matched_list.append(None)
                        debug_list.append(f\"Fallback scale={scale}\")

                tabla_sedes_servicio['_expected_daily_base'] = expected_daily_list
                tabla_sedes_servicio['_matched_standard_key'] = matched_list
                tabla_sedes_servicio['_debug'] = debug_list

                tabla_sedes_servicio = tabla_sedes_servicio.drop_duplicates(subset=['sede_id','Descripción del servicio','Cantidad del servicio']).reset_index(drop=True)
                # create label
                def make_label(r):
                    code = str(r.get(codigo_sede_col,'')) if codigo_sede_col in r.index else \"\"
                    num = str(r.get(numero_sede_col,'')) if numero_sede_col in r.index else \"\"
                    name = str(r.get(nombre_sede_col,'')) if nombre_sede_col in r.index else \"\"
                    if code and num:
                        return f\"{code}|{num} - {name}\" if name else f\"{code}|{num}\"
                    if code:
                        return f\"{code} - {name}\" if name else code
                    if name:
                        return name
                    return str(r.get('sede_id',''))
                tabla_sedes_servicio['_label'] = tabla_sedes_servicio.apply(make_label, axis=1)
                st.dataframe(tabla_sedes_servicio, use_container_width=True)
            else:
                st.info(\"Selecciona al menos un servicio para ver sedes que lo prestan.\")

            # Simulation block (same logic used before)
            st.subheader(\"Simulación de capacidad de atención\")
            if tabla_sedes_servicio.empty:
                st.info(\"No hay filas para simular.\")
                return

            # sede selection
            sede_unique_df = tabla_sedes_servicio.drop_duplicates(subset=['sede_id']).reset_index(drop=True)
            sede_options = sede_unique_df['_label'].tolist()
            sede_key_map = { row['_label']: row['sede_id'] for _, row in sede_unique_df.iterrows() }
            sede_options_with_all = [\"TODAS\"] + sorted(sede_options)
            sede_seleccionada = st.selectbox(\"Selecciona sede (o TODAS):\", options=sede_options_with_all, index=0)

            factor_operativo = filters.get(\"factor_operativo\", 1.0)

            if sede_seleccionada == \"TODAS\":
                sim_rows = tabla_sedes_servicio.copy().reset_index(drop=True)
            else:
                sid = sede_key_map.get(sede_seleccionada)
                sim_rows = tabla_sedes_servicio[tabla_sedes_servicio['sede_id'].astype(str) == str(sid)].copy()

            daily_list = []; weekly_list = []; monthly_list = []
            for _, row in sim_rows.iterrows():
                svc = str(row.get('Descripción del servicio',''))
                expected_base = row.get('_expected_daily_base', None)
                seed = hash_seed(nit_norm, row.get('sede_id',''), svc)
                rng = np.random.default_rng(seed)
                noise = rng.normal(loc=1.0, scale=0.05)
                utilization = max(0.1, factor_operativo * noise)

                if expected_base is not None:
                    daily_est = max(1, int(round(float(expected_base) * utilization)))
                else:
                    base_count = int(row.get('Cantidad del servicio', 0))
                    if base_count == 0:
                        base_count = 1
                    if base_count < 5:
                        scale = 5
                    else:
                        scale = min(20, max(5, int(base_count / 2)))
                    daily_est = max(1, int(round(base_count * scale * utilization)))

                weekly_est = daily_est * 7
                monthly_est = daily_est * 30
                daily_list.append(daily_est); weekly_list.append(weekly_est); monthly_list.append(monthly_est)

            sim_rows = sim_rows.reset_index(drop=True)
            sim_rows['Usuarios diarios estimados'] = daily_list
            sim_rows['Usuarios semanales estimados'] = weekly_list
            sim_rows['Usuarios mensuales estimados'] = monthly_list

            preferred = ['sede_id','codigo_sede','numero_sede','Departamento','Municipio','Nivel','nombre_sede','_label','Descripción del servicio','Cantidad del servicio','_expected_daily_base','_debug','Usuarios diarios estimados','Usuarios semanales estimados','Usuarios mensuales estimados']
            sim_display = sim_rows.loc[:, [c for c in preferred if c in sim_rows.columns] + [c for c in sim_rows.columns if c not in preferred]]

            st.dataframe(sim_display, use_container_width=True)

            # Atenciones por sede
            group_key = '_label' if '_label' in sim_display.columns else ('sede_id' if 'sede_id' in sim_display.columns else None)
            if group_key:
                atenciones_por_sede = sim_display.groupby(group_key)[['Usuarios diarios estimados','Usuarios semanales estimados','Usuarios mensuales estimados']].sum().reset_index()
                atenciones_por_sede = atenciones_por_sede.sort_values('Usuarios diarios estimados', ascending=False).reset_index(drop=True)
                atenciones_por_sede = atenciones_por_sede.rename(columns={group_key:'Sede','Usuarios diarios estimados':'Atenciones diarias estimadas','Usuarios semanales estimados':'Atenciones semanales estimadas','Usuarios mensuales estimados':'Atenciones mensuales estimadas'})
                st.subheader("Atenciones por sede (sumadas)")
                st.dataframe(atenciones_por_sede, use_container_width=True)

            # Resumen extendido (totales por servicio & nivel & sedes)
            total_daily = int(sim_display['Usuarios diarios estimados'].sum()) if 'Usuarios diarios estimados' in sim_display.columns else 0
            total_weekly = int(sim_display['Usuarios semanales estimados'].sum()) if 'Usuarios semanales estimados' in sim_display.columns else 0
            total_monthly = int(sim_display['Usuarios mensuales estimados'].sum()) if 'Usuarios mensuales estimados' in sim_display.columns else 0

            servicios_totales = pd.DataFrame()
            if 'Descripción del servicio' in sim_display.columns and 'Usuarios diarios estimados' in sim_display.columns:
                servicios_totales = sim_display.groupby('Descripción del servicio')['Usuarios diarios estimados'].sum().reset_index().rename(columns={'Usuarios diarios estimados':'Total diarios estimados'}).sort_values('Total diarios estimados', ascending=False)

            nivel_totales = pd.DataFrame()
            if 'Nivel' in sim_display.columns and 'Usuarios diarios estimados' in sim_display.columns:
                nivel_totales = sim_display.groupby('Nivel')['Usuarios diarios estimados'].sum().reset_index().rename(columns={'Usuarios diarios estimados':'Total diarios estimados'}).sort_values('Total diarios estimados', ascending=False)

            if 'sede_id' in sim_display.columns:
                involved_sedes = int(sim_display['sede_id'].nunique())
            elif 'nombre_sede' in sim_display.columns:
                involved_sedes = int(sim_display['nombre_sede'].nunique())
            else:
                involved_sedes = int(sim_display.shape[0])

            rows = [
                {'Métrica':'Cantidad de atenciones diarias','Total estimado': format_number(total_daily)},
                {'Métrica':'Cantidad de atenciones semanales','Total estimado': format_number(total_weekly)},
                {'Métrica':'Cantidad de atenciones mensuales','Total estimado': format_number(total_monthly)},
                {'Métrica':'Total de sedes analizadas','Total estimado': str(involved_sedes)},
            ]
            rows.append({'Métrica':'--- Totales por servicio (diarios) ---','Total estimado':''})
            for _, r in servicios_totales.iterrows():
                rows.append({'Métrica': f"Servicio: {r['Descripción del servicio']}", 'Total estimado': format_number(int(r['Total diarios estimados']))})
            rows.append({'Métrica':'--- Totales por Nivel de Atención (diarios) ---','Total estimado':''})
            if not nivel_totales.empty:
                for _, r in nivel_totales.iterrows():
                    rows.append({'Métrica': f"Nivel {r['Nivel']}", 'Total estimado': format_number(int(r['Total diarios estimados']))})
            resumen_atenciones_ext = pd.DataFrame(rows)
            st.subheader("Resumen de atenciones estimadas (extendido)")
            st.table(resumen_atenciones_ext)

            # Download button (pack sheets)
            sheets = {
                "Resumen": pd.DataFrame({'Métrica':['Total Sedes','Total Departamentos','Total Municipios'], 'Valor':[int(sede_unicas.shape[0]) if not sede_unicas.empty else involved_sedes, int(ips_rows['Departamento'].nunique()) if 'Departamento' in ips_rows.columns else 0, int(ips_rows['Municipio'].nunique()) if 'Municipio' in ips_rows.columns else 0]}),
                "Sedes": sede_unicas,
                "Simulacion": sim_display
            }
            if 'atenciones_por_sede' in locals() and not atenciones_por_sede.empty:
                sheets["Atenciones_por_sede"] = atenciones_por_sede
            if not servicios_totales.empty:
                sheets["Totales_por_servicio"] = servicios_totales
            if not nivel_totales.empty:
                sheets["Totales_por_nivel"] = nivel_totales
            tables_comp.download_excel(sheets, filename=f"simulacion_radiografia_{nit_norm}.xlsx")
        """),
    "app/main.py": textwrap.dedent("""\
        \"\"\"Entry point for the modular Streamlit app.
        Run:
            streamlit run app/main.py
        \"\"\"
        import streamlit as st
        from app.components import filters as filters_comp
        from importlib import import_module

        st.set_page_config(page_title=\"Dashboard IPS - Modular\", layout=\"wide\", page_icon=\"🏥\")

        st.sidebar.title(\"Dashboard — Menú principal\")
        menu = st.sidebar.radio(\"Selecciona módulo:\", [
            \"Análisis IPS\",
            \"Comparaciones de IPS\",
            \"Análisis por tipos de servicios\",
            \"Otros (xxxx)\",
            \"Otros (xxxx)\",
        ])

        # load common filters display (but pages will receive df to populate caches)
        page_map = {
            \"Análisis IPS\": \"app.pages.analysis_ips\",
            # placeholders for future pages:
            \"Comparaciones de IPS\": None,
            \"Análisis por tipos de servicios\": None,
            \"Otros (xxxx)\": None,
            \"Otros (xxxx)\": None,
        }

        module_path = page_map.get(menu)
        if module_path:
            module = import_module(module_path)
            # Each page exports run(filters)
            filters = filters_comp.sidebar_filters()
            module.run(filters)
        else:
            st.info(\"Página no implementada aún. Selecciona 'Análisis IPS' para ver el simulador migrado.\")
        """),
    "requirements.txt": textwrap.dedent("""\
        streamlit>=1.20
        pandas
        numpy
        openpyxl
        pyarrow
        """),
    "README.md": textwrap.dedent("""\
        # Dashboard IPS - Modular refactor

        This repository layout splits the monolithic Streamlit app into modules.

        Directory structure (final expected under your project root, or you can put under C:/REPS):
        - app/
          - main.py
          - config.py
          - data.py
          - utils.py
          - standards.py
          - components/
            - filters.py
            - tables.py
          - pages/
            - analysis_ips.py

        Setup instructions
        1. Create folders:
           - Option A: run the helper script (Windows):
             python create_project_structure.py
             This will create C:\\REPS and C:\\REPS\\data etc.

           - Option B: create folders manually.

        2. Place your dataset:
           - Preferred: Parquet file at:
             `C:\\REPS\\data\\output_data.parquet`
           - Or CSV at:
             `C:\\REPS\\data\\output_data.csv`
           - You can override the data directory by setting the environment variable `REPS_DATA_DIR` to another path (e.g. your project path).

        3. Install requirements:
           pip install -r requirements.txt

        4. Run the app:
           streamlit run app/main.py

        Notes
        - I preserved the simulation algorithm in `app/pages/analysis_ips.py`. It references the standards in `app/standards.py`.
        - The sidebar filters component shows "TODAS" as first option — selecting it means "no filter".
        - The code expects certain column names (many variants checked). If your dataset uses different column names, edit `app/pages/analysis_ips.py` to adjust the column detection list (there are comments near the top).
        """),
}

def ensure_dirs_and_write_files(base: Path, files_map: dict, overwrite: bool = True):
    for rel_path, content in files_map.items():
        target = base / rel_path
        target_parent = target.parent
        target_parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            print(f"Skipping existing file (overwrite disabled): {target}")
            continue
        # write text file (utf-8)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote: {target}")

def main():
    print(f"Creating project structure under: {BASE}")
    ensure_dirs_and_write_files(BASE, files, overwrite=OVERWRITE)
    print("\\nAll files written.")
    print("Next steps:")
    print(" - Place your dataset at C:/REPS/data/output_data.parquet (or output_data.csv).")
    print(" - From your terminal: pip install -r C:/REPS/requirements.txt")
    print(" - Run: streamlit run C:/REPS/app/main.py")

if __name__ == '__main__':
    main()
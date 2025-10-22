## Resumen

Breve descripción del cambio:
- Migración: wrappers para módulos legacy (analysis_ips, comparaciones, giro_directo).
- Reemplazo controlado de archivos core (main.py, master_ips_impl.py, master_ips_05.py, master_ips_export.py, master_ips.py).
- Añadido: CI workflow, Dockerfile, requirements.txt, pre-commit config y plantilla de PR.

## Qué se probó
- [ ] Ejecución local de Streamlit y prueba rápida de cada página.
- [ ] MASTER IPS ejecuta bloques 01→05 y genera ctx['outputs'].
- [ ] Generación de Excel (export) exitosa.
- [ ] Revisión de backups (.bak y .orig) y tar.gz creado.

## Checklist para el reviewer
- [ ] Revisar cambios en main.py y app/pagina/master_ips_impl.py (lógica crítica).
- [ ] Confirmar que los wrappers llaman a los .orig correspondientes sin romper UI.
- [ ] Validar que las rutas (GIRO_PARQUET, OUTPUT_PARQUET, SUGERIDOS_PATH) estén documentadas y configurables por env vars.
- [ ] Aceptar el merge solo después de pruebas manuales en staging.

## Pasos para probar localmente
1. En la rama feature (migration/wrappers-and-core):
   git checkout migration/wrappers-and-core
2. Instalar dependencias:
   pip install -r requirements.txt
3. Ejecutar app:
   streamlit run main.py
4. Abrir UI y revisar: Análisis IPS, Giro Directo, Comparaciones, MASTER IPS. Ejecutar MASTER IPS y descargar Excel.

## Rollback
- Restaurar archivos desde los .orig o .bak generados por el script:
  - Ej. renombrar comparaciones.orig.py → comparaciones.py
- O extraer backup tar.gz creado en la raíz.

## Notas
- Si aceptamos el merge, recomiendo configurar un deployment pipeline (Render/Cloud Run) que use Dockerfile y las env vars para rutas (OUTPUT_PARQUET, GIRO_PARQUET, SUGERIDOS_PATH).

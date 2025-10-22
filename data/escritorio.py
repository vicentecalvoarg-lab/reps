import pandas as pd

# Configuración: Cambia a False si NO quieres actualizar el Parquet
actualizar_parquet = True

# Diccionario exacto para servicios del REPS (basado en tu lista y Res. 3100/2019)
mapeo_exacto = {
    # SALAS
    'SALAS - Procedimientos': 2,
    'SALAS - Partos': 2,
    'SALAS - Quirófano': 3,
    'SALAS - Sala de Cirugía': 3,
    'SALAS - Sala de Radioterapia': 3,
    
    # CAMAS
    'CAMAS - TPR': 2,
    'CAMAS - Pediátrica': 2,
    'CAMAS - Adultos': 2,
    'CAMAS - Atención del Parto': 2,
    'CAMAS - Cuidado Intermedio Pediátrico': 2,
    'CAMAS - Cuidado Intermedio Adulto': 2,
    'CAMAS - Cuna Intermedia Pediátrica': 2,
    'CAMAS - Intermedia Adultos': 2,
    'CAMAS - SPA Básico Adultos': 1,
    'CAMAS - SPA Básico Pediátricos': 1,
    'CAMAS - Salud Mental Adulto': 2,
    'CAMAS - Incubadora Intermedia Neonatal': 2,
    'CAMAS - Incubadora Intensiva Neonatal': 3,
    'CAMAS - Intensiva Adultos': 3,
    'CAMAS - Cuna Básico Neonatal': 1,
    'CAMAS - Farmacodependencia': 2,
    'CAMAS - Salud Mental Pediátrico': 2,
    'CAMAS - SPA Adultos': 1,
    'CAMAS - Obstetricia': 2,
    'CAMAS - SPA Pediátricas': 1,
    'CAMAS - Incubadora Básico Neonatal': 1,
    'CAMAS - Cuna Intermedia Neonatal': 2,
    'CAMAS - Cuna Intensiva Neonatal': 3,
    'CAMAS - Paciente crónico sin ventilador': 1,
    'CAMAS - Cuidado Intermedio Neonatal': 2,
    'CAMAS - Cuidado Intensivo Neonatal': 3,
    'CAMAS - Cuidado Intensivo Adulto': 3,
    'CAMAS - Cuidado básico neonatal': 1,
    'CAMAS - Intermedia Pediátrica': 2,
    'CAMAS - Intensiva Pediátrica': 3,
    'CAMAS - Cuna Intensiva Pediátrica': 3,
    'CAMAS - Cuidado Intensivo Pediátrico': 3,
    'CAMAS - Transplante de progenitores hematopoyeticos': 3,
    'CAMAS - Intensiva Quemado Adulto': 3,
    'CAMAS - Intensiva Quemado pediátrica': 3,
    'CAMAS - Paciente crónico con ventilador': 3,
    
    # CAMILLAS
    'CAMILLAS - Observación Pediátrica': 2,
    'CAMILLAS - Observación Adultos Hombres': 2,
    'CAMILLAS - Observación Adultos Mujeres': 2,
    'CAMILLAS - Otras patologías': 2,
    'CAMILLAS - SPA': 1,
    
    # CONSULTORIOS
    'CONSULTORIOS - Urgencias': 2,
    'CONSULTORIOS - Consulta Externa': 1,
    
    # UNIDAD MOVIL
    'UNIDAD MOVIL - Unidad Móvil': 2,
    
    # AMBULANCIAS
    'AMBULANCIAS - Básica': 1,
    'AMBULANCIAS - Medicalizada': 3,
    
    # SILLAS
    'SILLAS - SPA': 1,
    'SILLAS - Sillas de Hemodiálisis': 3,
    'SILLAS - Sillas de Quimioterapia': 3,
    'SILLAS - Salud Mental': 2,
    'SILLAS - Otras patologías': 2,
}

# Función actualizada: Primero chequea exacto, luego keywords
def get_service_complexity(service_name):
    # Normalizar (lower y corregir acentos comunes si es necesario)
    service_lower = service_name.lower().replace('Ã¡', 'á').replace('Ã³', 'ó')  # Fix UTF-8 issues
    
    # Chequeo exacto
    service_key = service_name  # Usa el original para exact match
    if service_key in mapeo_exacto:
        return mapeo_exacto[service_key]
    
    service_lower = service_name.lower()
    
    # Alta complejidad (nivel 3)
    if any(keyword in service_lower for keyword in [
        'alta complejidad', 'cirugía mayor', 'oncología', 'urgencias alta', 'cuidados intensivos', 'uci', 
        'trasplante', 'diálisis', 'radioterapia', 'quimioterapia', 'cirugía cardiovascular', 
        'neurocirugía', 'hospitalización alta complejidad', 'transporte asistencial alta', 'intensiva',
        'cuidados intensivos neonatales', 'cirugía oncológica', 'terapia intensiva', 'quemado', 'ventilador'
    ]):
        return 3
    
    # Mediana complejidad (nivel 2)
    elif any(keyword in service_lower for keyword in [
        'mediana complejidad', 'cuidado intermedio', 'hospitalización mediana', 'cirugía menor', 
        'endoscopía', 'imagenología avanzada', 'laboratorio clínico especial', 
        'consulta especializada mediana', 'odontología mediana', 'transporte asistencial mediana',
        'atención prehospitalaria mediana', 'camas adultos', 'camas pediátrica', 
        'camillas observación', 'salas partos', 'salas procedimientos', 
        'consultorios urgencias', 'consulta externa especializada', 
        'hospitalización intermedio', 'cirugía ambulatoria', 'ecografía especializada',
        'endodoncia', 'extracciones complejas', 'estabilización básica avanzada', 'medicalizada'
    ]):
        return 2
    
    # Baja complejidad (nivel 1)
    elif any(keyword in service_lower for keyword in [
        'baja complejidad', 'consulta externa general', 'medicina general', 'odontología básica', 
        'vacunación', 'promoción salud', 'laboratorio básico', 'transporte asistencial baja',
        'consulta general', 'medicina familiar', 'odontología simple', 'básica'
    ]):
        return 1
    
    # Por defecto: 1
    else:
        print(f"Advertencia: Servicio no mapeado '{service_name}', asignado como 1 (baja). Agrega al diccionario.")
        return 1

# Resto del código igual (leer df, groupby, etc.)
df = pd.read_parquet('reps.parquet')
print(df.columns.tolist())
print(df.head())

df['ips_id'] = df['Código sede'].astype(str) + df['Número sede'].astype(str)
df['servicio_completo'] = df['nom grupo capacidad'] + ' - ' + df['nom descripcion capacidad']

grouped = df.groupby('ips_id').agg({
    'num nivel atencion': 'first',
    'servicio_completo': lambda x: list(set(x)),
    'Código sede': 'first',
    'Número sede': 'first'
}).reset_index()

def calculate_ips_level(services):
    if not services:
        return 1
    levels = [get_service_complexity(s) for s in services]
    return max(levels)

grouped['nivel_calculado'] = grouped['servicio_completo'].apply(calculate_ips_level)

grouped['valido'] = grouped['num nivel atencion'] == grouped['nivel_calculado']
grouped['razon'] = grouped.apply(lambda row: f"Nivel declarado {row['num nivel atencion']} no coincide con calculado {row['nivel_calculado']}" if not row['valido'] else 'Válido', axis=1)

invalidos = grouped[grouped['valido'] == False][[
    'ips_id', 'Código sede', 'Número sede', 'num nivel atencion', 'nivel_calculado', 
    'servicio_completo', 'razon'
]]

invalidos.to_csv('invalidos_ips.csv', index=False, encoding='utf-8')

if actualizar_parquet:
    print("\nActualizando el Parquet con niveles calculados para IPS inválidas...")
    correcciones = invalidos[['ips_id', 'nivel_calculado']].copy()
    correcciones.rename(columns={'nivel_calculado': 'nivel_corregido'}, inplace=True)
    df_actualizado = df.merge(correcciones, on='ips_id', how='left')
    mask_actualizar = df_actualizado['nivel_corregido'].notna()
    df_actualizado.loc[mask_actualizar, 'num nivel atencion'] = df_actualizado.loc[mask_actualizar, 'nivel_corregido']
    df_actualizado.drop('nivel_corregido', axis=1, inplace=True)
    df_actualizado.drop(['ips_id', 'servicio_completo'], axis=1, inplace=True)
    df_actualizado.to_parquet('reps.parquet', index=False)
    print(f"¡Parquet actualizado! {len(invalidos)} IPS corregidas.")
    df = df_actualizado
else:
    print("\nModo de solo lectura: No se actualizó el Parquet.")

total_ips = len(grouped)
invalidos_count = len(invalidos)
print(f"Total de IPS procesadas: {total_ips}")
print(f"IPS con niveles inválidos: {invalidos_count}")
print(f"Porcentaje inválidos: {invalidos_count / total_ips * 100:.2f}%")

print("\nDistribución de niveles calculados:")
print(grouped['nivel_calculado'].value_counts().sort_index())

print("\nPrimeros 5 inválidos:")
print(invalidos.head())
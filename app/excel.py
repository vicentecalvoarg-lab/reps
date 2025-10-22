import base64
import pandas as pd

# Datos CSV como string (de tu mensaje)
csv_data = """Servicio Completo,Mínimo Recomendado (por 100.000 hab.),Rango Normal (Baja/Normal/Alta),Umbral Alto (> por 100.000 hab.),Notas/Fuente
SALAS - Procedimientos,1.0,1-3,5,Proxy quirúrgicos menores; basado en WHO Global Surgery (1-2 salas mín. para LMICs).
CAMAS - TPR,1.0,1-5,10,Rehabilitación; proxy camas generales intermedias (WHO 200-300 total camas).
CAMAS - Pediátrica,20.0,20-50,100,Parte de camas pediátricas; ajustado de WHO (2-5% de camas totales pediátricas).
CAMAS - Adultos,100.0,100-200,300,"Camas hospitalarias generales; Colombia ~170 (WHO/PAHO, LMICs min 200)."
CAMAS - Atención del Parto,2.0,2-5,10,Obstetricia básica; proxy partos (PAHO ~5 camas/100k mujeres).
CAMILLAS - Observación Pediátrica,5.0,5-15,20,Observación urgencias pediátrica; proxy UCI pediátrica (WHO 2-5).
CAMILLAS - Observación Adultos Hombres,5.0,5-15,20,Observación adultos; proxy camas intermedias (PAHO).
CAMILLAS - Observación Adultos Mujeres,5.0,5-15,20,Igual que arriba.
CONSULTORIOS - Urgencias,5.0,5-10,20,Unidades urgencias; PAHO mediana complejidad (1-2 por 10k hab.).
CONSULTORIOS - Consulta Externa,50.0,50-100,200,Consultas primarias; proxy visitas ambulatorias (PAHO/WHO 1-2 visitas/persona/año).
SALAS - Partos,1.0,1-2,5,Salas obstetricia; WHO Global Surgery (mín. para partos).
UNIDAD MOVIL - Unidad Móvil,0.5,0.5-1,2,Transporte móvil; proxy ambulancias (WHO 1/100k).
CAMAS - Cuidado Intermedio Pediátrico,2.0,2-5,10,UCI intermedia pediátrica; ajustado WHO (5-10 UCI total pediátrica).
CAMAS - Cuidado Intermedio Adulto,5.0,5-10,15,UCI intermedia adultos; WHO global mean 8.7 ICU.
CAMAS - Cuna Intermedia Pediátrica,1.0,1-3,5,Neonatal intermedia; proxy NICU (5-10 per 100k).
SALAS - Quirófano,1.0,1-2,5,Quirófano mayor; WHO 1-2 salas/100k para LMICs.
SALAS - Sala de Cirugía,1.0,1-2,5,Igual que quirófano; basado en procedimientos 3384/100k (Lancet Comm.).
AMBULANCIAS - Básica,1.0,1-2,3,Ambulancias básicas; WHO min 1/100k.
CAMAS - Intermedia Adultos,5.0,5-10,15,Hospitalización intermedia; PAHO complejidad mediana.
CAMAS - SPA Básico Adultos,2.0,2-5,10,Procedimientos ambulatorios; proxy quirúrgicos bajos.
CAMAS - SPA Básico Pediátricos,1.0,1-3,5,Pediátrico básico; ajustado WHO pediátrico.
SILLAS - SPA,2.0,2-5,10,Procedimientos en sillas; proxy ambulatorio.
SILLAS - Sillas de Hemodiálisis,20.0,20-30,50,"Hemodiálisis; basado en prevalencia CKD (PAHO 473 pmp, ~20 estaciones)."
CAMAS - Salud Mental Adulto,10.0,10-20,30,Camas psiquiátricas; WHO min 30-60 total psych beds/100k.
AMBULANCIAS - Medicalizada,1.0,1-2,3,Medicalizadas; WHO 1-2/100k avanzadas.
CAMAS - Incubadora Intermedia Neonatal,2.0,2-5,10,NICU intermedia; ajustado de US data (~5-10 NICU/100k).
CAMAS - Incubadora Intensiva Neonatal,3.0,3-5,10,NICU intensiva; WHO ~5 per 1k births (proxy pop).
CAMAS - Intensiva Adultos,5.0,5-10,15,UCI adultos; WHO mean 8.7.
CAMAS - Cuna Básico Neonatal,2.0,2-5,10,Neonatal básica; PAHO.
SILLAS - Sillas de Quimioterapia,10.0,10-20,30,Quimioterapia; proxy oncología (prevalencia cáncer WHO).
CAMAS - Farmacodependencia,1.0,1-5,10,Adicciones; parte de psych beds (WHO 30-60).
CAMAS - Salud Mental Pediátrico,2.0,2-5,10,Psych pediátrico; ajustado WHO.
CAMAS - SPA Adultos,2.0,2-5,10,Procedimientos adultos; proxy.
SILLAS - Salud Mental,5.0,5-10,20,Sillas psych; parte de total psych (WHO).
CAMAS - Obstetricia,5.0,5-10,20,Maternidad; PAHO ~5-10 camas/100k mujeres (ajustado pop).
CAMAS - SPA Pediátricas,1.0,1-3,5,Pediátrico ambulatorio.
CAMAS - Incubadora Básico Neonatal,2.0,2-5,10,Neonatal básica.
CAMAS - Cuna Intermedia Neonatal,2.0,2-5,10,Intermedia neonatal.
CAMAS - Cuna Intensiva Neonatal,3.0,3-5,10,Intensiva neonatal.
CAMAS - Paciente crónico sin ventilador,5.0,5-10,20,Crónicos básicos; proxy camas generales.
CAMILLAS - Otras patologías,5.0,5-15,20,Observación general.
CAMAS - Cuidado Intermedio Neonatal,2.0,2-5,10,Neonatal intermedia.
CAMAS - Cuidado Intensivo Neonatal,3.0,3-5,10,NICU intensiva.
CAMAS - Cuidado Intensivo Adulto,5.0,5-10,15,UCI adultos.
CAMAS - Cuidado básico neonatal,2.0,2-5,10,Neonatal básica.
SALAS - Sala de Radioterapia,0.5,0.5-1,2,Radioterapia; WHO oncología min (raro en LMICs).
CAMAS - Intermedia Pediátrica,2.0,2-5,10,UCI intermedia pediátrica.
CAMAS - Intensiva Pediátrica,2.0,2-5,10,UCI pediátrica; WHO ~2-5/100k.
CAMAS - Cuna Intensiva Pediátrica,1.0,1-3,5,Pediátrica intensiva.
CAMAS - Cuidado Intensivo Pediátrico,2.0,2-5,10,UCI pediátrica.
CAMAS - Transplante de progenitores hematopoyeticos,0.1,0.1-0.5,1,Trasplantes raros; WHO especializado.
CAMAS - Intensiva Quemado Adulto,0.5,0.5-1,2,Quemados UCI; especializado.
CAMAS - Intensiva Quemado pediátrica,0.2,0.2-0.5,1,Pediátrico quemados.
CAMILLAS - SPA,2.0,2-5,10,Procedimientos en camillas.
CAMAS - Paciente crónico con ventilador,1.0,1-3,5,Crónicos ventilados; proxy UCI.
SILLAS - Otras patologías,5.0,5-10,20,Patologías intermedias; proxy psych/general."""

# Crear DataFrame desde CSV string
from io import StringIO
df = pd.read_csv(StringIO(csv_data))

# Guardar como Excel
df.to_excel('benchmarks.xlsx', index=False, sheet_name='Benchmarks')

print("¡Archivo benchmarks.xlsx creado exitosamente!")
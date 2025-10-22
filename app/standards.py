"""Service standards mapping and lookup.
Keep this file focused on the service_standard_map and the matching logic.
"""
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
                return {"unit_type": unit_type, "daily_per_unit": daily_per_unit, "matched_key": k}
    return None

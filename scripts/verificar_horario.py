"""
Revisa si, segun el horario fijo de publicacion (hora Chile, invierno
UTC-4), hay algun tema de hoy que ya deberia haberse publicado y todavia
no se publico. Lo usa publicar_diario.yml, que ahora corre cada 15
minutos en vez de tener 10 horarios de cron exactos -- GitHub a veces
retrasa o se salta ejecuciones programadas cuando hay mucha carga en su
cola global, y este mecanismo de "catch-up" evita que un tema se pierda
por completo: si su horario ya paso y no se publico, se publica en la
siguiente revision (maximo ~15 minutos de atraso).

No modifica estado_publicaciones.json -- solo lo lee. El que lo actualiza
es marcar_publicado.py, despues de una publicacion exitosa.
"""
import json
import os
from datetime import datetime, timedelta, timezone

ARCHIVO_ESTADO = "estado_publicaciones.json"

# (tema_id, hora, minuto) en hora de Chile. OJO: calculado para invierno
# (UTC-4). Cuando Chile entre en horario de verano (UTC-3, oct-mar), hay
# que cambiar OFFSET_CHILE de -4 a -3 horas para mantener la misma hora
# local -- si no se ajusta, todo se correra 1 hora mas tarde en la
# practica (no se pierde nada, solo se publica una hora "tarde").
HORARIOS_CHILE = [
    (1, 0, 0),
    (2, 2, 30),
    (3, 5, 0),
    (4, 7, 30),
    (5, 10, 0), 
    (6, 12, 0),
    (7, 14, 30),
    (8, 17, 0),
    (9, 19, 30),
    (10, 22, 0),
]

OFFSET_CHILE = timedelta(hours=-4)


def main():
    ahora_utc = datetime.now(timezone.utc)
    ahora_chile = ahora_utc + OFFSET_CHILE
    fecha_chile = ahora_chile.date().isoformat()

    if os.path.exists(ARCHIVO_ESTADO):
        with open(ARCHIVO_ESTADO) as f:
            estado = json.load(f)
    else:
        estado = {}

    if estado.get("fecha_chile") != fecha_chile:
        # Dia nuevo (hora Chile): todavia no se publico ningun tema hoy.
        estado = {"fecha_chile": fecha_chile, "publicados": []}

    tema_pendiente = None
    for tema_id, hora, minuto in HORARIOS_CHILE:
        objetivo = ahora_chile.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if ahora_chile >= objetivo and tema_id not in estado["publicados"]:
            tema_pendiente = tema_id
            break  # el pendiente mas antiguo primero, uno por ejecucion

    github_output = os.environ.get("GITHUB_OUTPUT")
    if tema_pendiente:
        print(f"✅ Tema pendiente: {tema_pendiente} (hora Chile actual: {ahora_chile.strftime('%H:%M')}, fecha: {fecha_chile})")
        if github_output:
            with open(github_output, "a") as f:
                f.write("hay_pendiente=true\n")
                f.write(f"tema_id={tema_pendiente}\n")
    else:
        print(f"⏳ No hay temas pendientes por ahora (hora Chile actual: {ahora_chile.strftime('%H:%M')}, fecha: {fecha_chile}, ya publicados hoy: {estado.get('publicados', [])})")
        if github_output:
            with open(github_output, "a") as f:
                f.write("hay_pendiente=false\n")


if __name__ == "__main__":
    main()

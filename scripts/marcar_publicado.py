"""
Marca un tema como ya publicado hoy en estado_publicaciones.json. Se llama
SOLO despues de que generar_reel_v2.py termino con exito, y solo en runs
automaticos (no en pruebas manuales con --tema), para no gastar el turno
de un tema real con una ejecucion de prueba.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ARCHIVO_ESTADO = "estado_publicaciones.json"
OFFSET_CHILE = timedelta(hours=-4)


def main():
    if len(sys.argv) < 2:
        print("Uso: python marcar_publicado.py <tema_id>")
        sys.exit(1)

    tema_id = int(sys.argv[1])
    ahora_chile = datetime.now(timezone.utc) + OFFSET_CHILE
    fecha_chile = ahora_chile.date().isoformat()

    if os.path.exists(ARCHIVO_ESTADO):
        with open(ARCHIVO_ESTADO) as f:
            estado = json.load(f)
    else:
        estado = {}

    if estado.get("fecha_chile") != fecha_chile:
        estado = {"fecha_chile": fecha_chile, "publicados": []}

    if tema_id not in estado["publicados"]:
        estado["publicados"].append(tema_id)

    with open(ARCHIVO_ESTADO, "w") as f:
        json.dump(estado, f, indent=2)

    print(f"✅ Estado actualizado: {estado}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Comprobaciones de integridad del repositorio de Azure Data Factory.

ADF-05  Artefacto fuera de las carpetas que crea el Studio.
ADF-06  El nombre del archivo no coincide con la propiedad name del JSON.

Ninguna de las dos figura en el Checklist v2: se reportan como
informativas y no bloquean el pase. Devuelve siempre codigo 0.
"""

import json
import os
import sys

RUTA_CONFIG = "config/adf_listas.json"
RUTA_SALIDA = "hallazgos_adf_repo.json"


def cargar_config(ruta=RUTA_CONFIG):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def normalizar(ruta):
    return ruta.replace("\\", "/").strip("/")


def hallazgo(cfg, archivo, mensaje, evidencia):
    return {
        "regla_id": cfg["id"],
        "checklist_nro": cfg.get("checklist_nro"),
        "criticidad": cfg.get("criticidad", "OPC"),
        "archivo": archivo,
        "mensaje": mensaje,
        "evidencia": evidencia,
    }


def validar_ubicacion(bloque, rel):
    """ADF-05: el artefacto vive en una carpeta oficial de Data Factory."""
    cfg = bloque["artefacto_fuera_de_carpeta"]
    partes = normalizar(rel).split("/")

    if len(partes) == 1:
        if partes[0] in bloque["archivos_permitidos_en_raiz"]:
            return []
        return [hallazgo(cfg, rel,
                         "Archivo JSON en la raiz del repositorio.",
                         "Data Factory no reconoce artefactos fuera de sus carpetas")]

    if partes[0] not in bloque["carpetas_oficiales"]:
        return [hallazgo(cfg, rel,
                         "El artefacto no esta en una carpeta oficial de Data Factory.",
                         f"carpeta '{partes[0]}' no la genera el Studio")]
    return []


def validar_nombre(bloque, raiz, rel):
    """ADF-06: el nombre del archivo coincide con la propiedad name."""
    cfg = bloque["nombre_no_coincide"]
    ruta = os.path.join(raiz, rel)
    if not os.path.isfile(ruta):
        return []

    try:
        with open(ruta, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return [{"regla_id": "ADF-00", "checklist_nro": None, "criticidad": "OPC",
                 "archivo": rel, "mensaje": "No se pudo leer el JSON del artefacto.",
                 "evidencia": str(e)[:120]}]

    nombre_json = doc.get("name")
    if not nombre_json:
        return [hallazgo(cfg, rel,
                         "El artefacto no declara la propiedad name.",
                         "el Studio siempre la escribe")]

    nombre_archivo = os.path.splitext(os.path.basename(rel))[0]
    if nombre_json != nombre_archivo:
        return [hallazgo(cfg, rel,
                         "El nombre del archivo no coincide con la propiedad name.",
                         f"archivo '{nombre_archivo}' contra name '{nombre_json}'")]
    return []


def reportar(hallazgos):
    if not hallazgos:
        print("Sin observaciones de integridad del repositorio.")
        return

    por_archivo = {}
    for h in hallazgos:
        por_archivo.setdefault(h["archivo"], []).append(h)

    for archivo, lista in sorted(por_archivo.items()):
        print(f"\n{archivo}")
        for h in lista:
            print(f"  [OPC] {h['regla_id']}  {h['mensaje']}")
            print(f"        {h['evidencia']}")

    print(f"\nTotal: {len(hallazgos)} observaciones informativas.")


def main():
    args = [a for a in sys.argv[1:] if a.strip()]
    raiz = "."
    if args and os.path.isdir(args[0]):
        raiz = args[0]
        args = args[1:]

    ruta_cfg = os.path.join(raiz, RUTA_CONFIG)
    cfg = cargar_config(ruta_cfg if os.path.isfile(ruta_cfg) else RUTA_CONFIG)
    bloque = cfg.get("integridad_repo")
    if not bloque:
        print("El catalogo no tiene el bloque de integridad. Nada que validar.")
        return 0

    hallazgos = []
    for rel in args:
        rel = normalizar(rel)
        if not rel.lower().endswith(".json"):
            continue
        # Los archivos que genera la propia integracion con Git no son artefactos
        if os.path.basename(rel) in bloque["archivos_permitidos_en_raiz"]:
            continue
        hallazgos += validar_ubicacion(bloque, rel)
        hallazgos += validar_nombre(bloque, raiz, rel)

    reportar(hallazgos)

    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(hallazgos, f, ensure_ascii=False, indent=2)

    # Informativo: nunca bloquea el pase.
    return 0


if __name__ == "__main__":
    sys.exit(main())

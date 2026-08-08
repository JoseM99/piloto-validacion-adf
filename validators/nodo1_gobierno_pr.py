#!/usr/bin/env python3
"""Validador de las reglas de GitHub del Checklist v2 (filas 1 y 2).

GIT-01  La rama sigue la nomenclatura feature/* o fix/*.
GIT-02  El Pull Request trae la estructura completa del pase.

No mira archivos: solo la rama, el titulo y la descripcion del Pull
Request, que llegan por variables de entorno desde el workflow.
"""

import json
import os
import re
import sys
import unicodedata

RUTA_CONFIG = "config/adf_listas.json"
RUTA_SALIDA = "hallazgos_gobierno.json"


def cargar_config(ruta=RUTA_CONFIG):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def sin_tildes(texto):
    base = unicodedata.normalize("NFD", texto)
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def normalizar(texto):
    return sin_tildes(texto or "").lower()


def hallazgo(cfg, mensaje, evidencia):
    return {
        "regla_id": cfg["id"],
        "checklist_nro": cfg.get("checklist_nro"),
        "criticidad": cfg.get("criticidad", "OBL"),
        "mensaje": mensaje,
        "evidencia": evidencia,
    }


def validar_rama(cfg, rama):
    """GIT-01 (fila 1): nomenclatura feature/* o fix/*."""
    out = []
    if not rama:
        return [hallazgo(cfg, "No se pudo leer el nombre de la rama.", "sin dato")]

    prefijo = next((p for p in cfg["prefijos"] if rama.startswith(p)), None)
    if prefijo is None:
        esperados = " o ".join(cfg["prefijos"])
        return [hallazgo(cfg, f"La rama no empieza con {esperados}.", f"rama = '{rama}'")]

    descripcion = rama[len(prefijo):]
    if not descripcion:
        out.append(hallazgo(cfg, "La rama no tiene descripcion despues del prefijo.",
                            f"rama = '{rama}'"))
    elif not re.match(cfg["patron_descripcion"], descripcion):
        out.append(hallazgo(cfg,
                            "La descripcion de la rama debe ir en minusculas y separada por guiones.",
                            f"rama = '{rama}'  ·  ejemplo: {cfg['_ejemplo']}"))
    return out


def validar_estructura(cfg, cuerpo):
    """GIT-02 (fila 2): el Pull Request declara la estructura del pase."""
    out = []
    texto = (cuerpo or "").strip()

    if not texto:
        return [hallazgo(cfg, "El Pull Request no tiene descripcion.",
                         "debe usarse la plantilla del pase")]

    if len(texto) < cfg["largo_minimo_descripcion"]:
        out.append(hallazgo(cfg, "La descripcion del Pull Request es demasiado breve.",
                            f"{len(texto)} caracteres; minimo {cfg['largo_minimo_descripcion']}"))

    plano = normalizar(texto)

    faltantes = [s for s in cfg["secciones"] if normalizar(s) not in plano]
    if faltantes:
        out.append(hallazgo(cfg, "Faltan secciones de la plantilla del pase.",
                            "faltan: " + ", ".join(faltantes)))

    sin_valor = []
    for campo in cfg["campos_datos_generales"]:
        clave = normalizar(campo)
        if clave not in plano:
            sin_valor.append(f"{campo} (ausente)")
            continue
        # Se toma el resto de la linea y se limpian separadores de tabla
        patron = re.escape(clave) + r"([^\n]*)"
        m = re.search(patron, plano)
        valor = (m.group(1) if m else "").strip(" |:-*_")
        if not valor:
            sin_valor.append(f"{campo} (sin completar)")
    if sin_valor:
        out.append(hallazgo(cfg, "Los datos generales del pase estan incompletos.",
                            "; ".join(sin_valor)))

    return out


def reportar(hallazgos):
    if not hallazgos:
        print("Gobierno del Pull Request: APROBADO. Sin hallazgos.")
        return

    for h in hallazgos:
        nro = h["checklist_nro"]
        ref = f" (checklist {nro})" if nro else ""
        print(f"  [OBL] {h['regla_id']}{ref}  {h['mensaje']}")
        print(f"        {h['evidencia']}")
    print(f"\nTotal: {len(hallazgos)} obligatorios.")


def main():
    cfg = cargar_config()
    bloque = cfg.get("gobierno_pr")
    if not bloque:
        print("El catalogo no tiene el bloque gobierno_pr. Nada que validar.")
        return 0

    rama = os.environ.get("PR_RAMA", "").strip()
    cuerpo = os.environ.get("PR_CUERPO", "")

    print(f"Rama: {rama or '(sin dato)'}\n")

    hallazgos = []
    hallazgos += validar_rama(bloque["rama"], rama)
    hallazgos += validar_estructura(bloque["estructura_pr"], cuerpo)

    reportar(hallazgos)

    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(hallazgos, f, ensure_ascii=False, indent=2)

    return 1 if hallazgos else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Validador determinista de artefactos de Azure Data Factory.

Aplica las cuatro reglas de ADF del Checklist v2 (filas 3 a 6) sobre los
archivos JSON que llegan en el Pull Request.
"""

import json
import os
import sys

RUTA_CONFIG = "config/adf_listas.json"
RUTA_SALIDA = "hallazgos_adf.json"


# ---------------------------------------------------------------- utilidades

def cargar_config(ruta=RUTA_CONFIG):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def igual(a, b, sensible):
    """Compara dos cadenas respetando o no las mayusculas."""
    return a == b if sensible else a.casefold() == b.casefold()


def esta_en(valor, lista, sensible):
    return any(igual(valor, x, sensible) for x in lista)


def leer_artefacto(ruta):
    """Devuelve (nombre, carpeta) del JSON. carpeta es None si esta en la raiz."""
    with open(ruta, encoding="utf-8") as f:
        doc = json.load(f)
    nombre = doc.get("name") or os.path.splitext(os.path.basename(ruta))[0]
    carpeta = (doc.get("properties") or {}).get("folder", {}).get("name")
    return nombre, carpeta


def hallazgo(regla, cfg_regla, archivo, mensaje, evidencia):
    return {
        "regla_id": regla,
        "checklist_nro": cfg_regla.get("checklist_nro"),
        "criticidad": cfg_regla.get("criticidad", "OBL"),
        "archivo": archivo,
        "mensaje": mensaje,
        "evidencia": evidencia,
    }


# ------------------------------------------------------------------- reglas

def validar_carpeta(cfg_regla, archivo, carpeta, sensible, etiqueta):
    """ADF-01 y ADF-03: el artefacto vive en una carpeta del estandar."""
    rid = cfg_regla["id"]
    out = []

    if not carpeta:
        out.append(hallazgo(
            rid, cfg_regla, archivo,
            f"El {etiqueta} esta en la raiz del arbol de ADF, sin carpeta asignada.",
            "propiedad 'folder' ausente en el JSON"))
        return out

    # Catalogo cerrado de rutas completas (datasets)
    if "rutas_validas" in cfg_regla:
        if not esta_en(carpeta, cfg_regla["rutas_validas"], sensible):
            out.append(hallazgo(
                rid, cfg_regla, archivo,
                "La carpeta no corresponde a una ruta estandar de datasets.",
                f"folder = '{carpeta}'"))
        return out

    # Catalogo por niveles (pipelines)
    niveles = [n for n in carpeta.split("/") if n]

    if not esta_en(niveles[0], cfg_regla["nivel_1"], sensible):
        out.append(hallazgo(
            rid, cfg_regla, archivo,
            "El primer nivel de la carpeta no es una funcionalidad valida.",
            f"folder = '{carpeta}'"))

    if len(niveles) >= 2:
        if not esta_en(niveles[1], cfg_regla["nivel_2"], sensible):
            out.append(hallazgo(
                rid, cfg_regla, archivo,
                "El segundo nivel de la carpeta no es una aplicacion valida.",
                f"folder = '{carpeta}'"))
    elif cfg_regla.get("nivel_2_requerido"):
        out.append(hallazgo(
            rid, cfg_regla, archivo,
            "Falta el segundo nivel de carpeta con la aplicacion.",
            f"folder = '{carpeta}'"))

    return out


def validar_nombre_pipeline(cfg_regla, archivo, nombre, sensible):
    """ADF-02: pipeline_[funcionalidad]_[aplicacion]_[tipo]."""
    rid = cfg_regla["id"]
    out = []
    partes = nombre.split(cfg_regla["separador"])

    if not partes or not igual(partes[0], cfg_regla["prefijo"], sensible):
        out.append(hallazgo(
            rid, cfg_regla, archivo,
            f"El nombre no empieza con el prefijo '{cfg_regla['prefijo']}'.",
            f"name = '{nombre}'"))
        return out

    if len(partes) < 3:
        out.append(hallazgo(
            rid, cfg_regla, archivo,
            "El nombre no tiene los segmentos minimos del estandar.",
            f"name = '{nombre}'"))
        return out

    funcs = cfg_regla["funcionalidades"]
    clave = next((k for k in funcs if igual(partes[1], k, sensible)), None)

    if clave is None:
        out.append(hallazgo(
            rid, cfg_regla, archivo,
            "La funcionalidad del nombre no es valida.",
            f"segmento '{partes[1]}' en '{nombre}'"))
        return out

    # Los pipelines master llevan el resto libre
    if funcs[clave]["segmentos_despues_de_funcionalidad"] == "libre":
        return out

    if not esta_en(partes[2], cfg_regla["aplicaciones"], sensible):
        out.append(hallazgo(
            rid, cfg_regla, archivo,
            "La aplicacion del nombre no esta en el catalogo.",
            f"segmento '{partes[2]}' en '{nombre}'"))

    # El tipo de carga solo se evalua si el estandar ya lo definio
    tipos = cfg_regla.get("tipos_carga") or []
    if tipos:
        if len(partes) < 4:
            out.append(hallazgo(
                rid, cfg_regla, archivo,
                "Falta el segmento de tipo de carga.",
                f"name = '{nombre}'"))
        elif not esta_en(partes[3], tipos, sensible):
            out.append(hallazgo(
                rid, cfg_regla, archivo,
                "El tipo de carga no esta en el catalogo.",
                f"segmento '{partes[3]}' en '{nombre}'"))

    return out


def validar_nombre_dataset(cfg_regla, archivo, nombre, sensible):
    """ADF-04: ds_[tipo]_[aplicacion]_[conexion]."""
    rid = cfg_regla["id"]
    out = []
    partes = nombre.split(cfg_regla["separador"])

    if not partes or not igual(partes[0], cfg_regla["prefijo"], sensible):
        out.append(hallazgo(
            rid, cfg_regla, archivo,
            f"El nombre no empieza con el prefijo '{cfg_regla['prefijo']}'.",
            f"name = '{nombre}'"))
        return out

    if len(partes) != 4:
        out.append(hallazgo(
            rid, cfg_regla, archivo,
            "El nombre no tiene los cuatro segmentos del estandar.",
            f"name = '{nombre}'"))
        return out

    campos = [("tipos", partes[1], "El tipo de dataset no esta en el catalogo."),
              ("aplicaciones", partes[2], "La aplicacion no esta en el catalogo."),
              ("conexiones", partes[3], "La conexion debe ser 'in' o 'out'.")]

    for clave, valor, msg in campos:
        if not esta_en(valor, cfg_regla[clave], sensible):
            out.append(hallazgo(rid, cfg_regla, archivo, msg,
                                f"segmento '{valor}' en '{nombre}'"))

    return out


# ----------------------------------------------------------------- ejecucion

def clasificar(ruta, cfg):
    """Devuelve 'pipeline', 'dataset' o None segun la carpeta raiz del repo."""
    raiz = ruta.replace("\\", "/").split("/")[0]
    for tipo, carpeta in cfg["carpetas_raiz_repo"].items():
        if tipo.startswith("_"):
            continue
        if raiz == carpeta:
            return tipo
    return None


def validar_archivo(ruta, cfg):
    tipo = clasificar(ruta, cfg)
    if tipo is None:
        return []

    sensible = cfg["opciones"]["comparacion_sensible_a_mayusculas"]

    try:
        nombre, carpeta = leer_artefacto(ruta)
    except (OSError, json.JSONDecodeError) as e:
        return [{
            "regla_id": "ADF-00", "checklist_nro": None, "criticidad": "OBL",
            "archivo": ruta, "mensaje": "No se pudo leer el JSON del artefacto.",
            "evidencia": str(e)[:120],
        }]

    bloque = cfg[tipo]
    etiqueta = "pipeline" if tipo == "pipeline" else "dataset"

    out = validar_carpeta(bloque["regla_carpeta"], ruta, carpeta, sensible, etiqueta)
    if tipo == "pipeline":
        out += validar_nombre_pipeline(bloque["regla_nombre"], ruta, nombre, sensible)
    else:
        out += validar_nombre_dataset(bloque["regla_nombre"], ruta, nombre, sensible)
    return out


def reportar(hallazgos):
    obl = [h for h in hallazgos if h["criticidad"] == "OBL"]
    opc = [h for h in hallazgos if h["criticidad"] != "OBL"]

    if not hallazgos:
        print("Sin hallazgos deterministas en los artefactos de Data Factory.")
        return

    por_archivo = {}
    for h in hallazgos:
        por_archivo.setdefault(h["archivo"], []).append(h)

    for archivo, lista in por_archivo.items():
        print(f"\n{archivo}")
        for h in lista:
            marca = "OBL" if h["criticidad"] == "OBL" else "OPC"
            nro = h["checklist_nro"]
            ref = f" (checklist {nro})" if nro else ""
            print(f"  [{marca}] {h['regla_id']}{ref}  {h['mensaje']}")
            print(f"        {h['evidencia']}")

    print(f"\nTotal: {len(obl)} obligatorios, {len(opc)} opcionales.")


def main():
    archivos = [a for a in sys.argv[1:] if a.strip()]
    if not archivos:
        print("Sin archivos que validar.")
        return 0

    cfg = cargar_config()

    hallazgos = []
    for ruta in archivos:
        if os.path.isfile(ruta):
            hallazgos += validar_archivo(ruta, cfg)

    reportar(hallazgos)

    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(hallazgos, f, ensure_ascii=False, indent=2)

    return 1 if any(h["criticidad"] == "OBL" for h in hallazgos) else 0


if __name__ == "__main__":
    sys.exit(main())

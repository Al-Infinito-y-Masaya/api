from base64 import b64decode, b64encode
from dataclasses import fields, replace
from hashlib import sha256
from http import HTTPStatus
from json import dumps
from typing import TYPE_CHECKING

from django.core.cache import cache
from numpy import asarray

from api_exceptions.errors import ApiError, NotFoundError
from mangroove_analisis.enums import EstadoCorrida
from mangroove_analisis.models import Corrida, ResultadoCelda, ResultadoEstanque
from mangroove_analisis.services import cubo_de
from mangroove_comun.medios import url_publica
from mangroove_insumos.services import auxiliares_de
from mangroove_motor.analisis import Resultado, analizar
from mangroove_motor.capas import capa_desconexion, codigos_conexion
from mangroove_motor.datos import Fecha, Pila
from mangroove_motor.perfil import Perfil
from mangroove_publicacion.contrato import Base, celda, manifiesto
from mangroove_publicacion.enums import POR_FECHA, FormatoArtefacto, TipoArtefacto
from mangroove_publicacion.models import Artefacto
from mangroove_regiones.models import Celda, Region

if TYPE_CHECKING:
    from mangroove_motor.grilla import Grilla

########################################################################################

INMUTABLE: str = "public, max-age=31536000, immutable"
BREVE: str = "public, max-age=300"

SEGUNDOS_EXPLORACION: int = 24 * 3600

ORDENES_ESTANQUES: dict[str, str] = {
    "area": "-area_ha",
    "distancia": "dist_canal_km",
    "inundacion": "-if_vecino",
    "puntaje": "-puntaje",
}

########################################################################################


class RetiradaError(ApiError):
    default_detail: str = "La versión pedida fue retirada."

    default_http_status: HTTPStatus = HTTPStatus.GONE


########################################################################################


def etiqueta(*partes: object) -> str:
    return (
        '"' + sha256(":".join(str(p) for p in partes).encode()).hexdigest()[:32] + '"'
    )


def region_activa(codigo: str) -> Region:
    region: Region | None = Region.objects.filter(codigo=codigo, is_active=True).first()

    if region is None:
        raise NotFoundError(detail=f"No existe la región {codigo!r}.")

    return region


def vigente(codigo: str) -> Corrida:
    corrida: Corrida | None = (
        Corrida.objects
        .select_related("region", "perfil")
        .filter(region__codigo=codigo, region__is_active=True, vigente=True)
        .first()
    )

    if corrida is None:
        raise NotFoundError(
            detail=f"La región {codigo!r} no tiene una versión publicada."
        )

    return corrida


def publicada(codigo: str, version: str) -> Corrida:
    corrida: Corrida | None = (
        Corrida.objects
        .select_related("region", "perfil")
        .filter(region__codigo=codigo, version=version)
        .first()
    )

    if corrida is None or corrida.estado not in {
        EstadoCorrida.PUBLICADA,
        EstadoCorrida.RETIRADA,
    }:
        raise NotFoundError(detail=f"No existe la versión {version} de {codigo!r}.")

    if corrida.estado == EstadoCorrida.RETIRADA:
        raise RetiradaError(detail=f"La versión {version} de {codigo!r} fue retirada.")

    return corrida


########################################################################################


def regiones() -> list[dict]:
    salida: list[dict] = []

    for corrida in (
        Corrida.objects
        .select_related("region")
        .filter(vigente=True, region__is_active=True)
        .order_by("region__codigo")
    ):
        region: Region = corrida.region

        salida.append(
            {
                "codigo": region.codigo,
                "nombre": region.nombre,
                "bbox": [
                    region.lon_min,
                    region.lat_min,
                    region.lon_max,
                    region.lat_max,
                ],
                "centro": [region.centro_lon, region.centro_lat],
                "zoom_inicial": region.zoom_inicial,
                "version": corrida.version,
                "publicada": corrida.publicada_at.isoformat()
                if corrida.publicada_at
                else None,
            },
        )

    return salida


def manifiesto_de(codigo: str, version: str) -> dict:
    return manifiesto(publicada(codigo, version), Base.API)


def url_capa(codigo: str, version: str, capa: str, fecha: str = "") -> str:
    corrida: Corrida = publicada(codigo, version)

    if (capa in POR_FECHA) != bool(fecha):
        raise NotFoundError(detail=f"La capa {capa!r} no existe en esta ruta.")

    filtro: dict = {"corrida": corrida, "formato": FormatoArtefacto.PNG, "tipo": capa}

    if fecha:
        filtro["corrida_fecha__fecha_codigo"] = fecha

    artefacto: Artefacto | None = (
        Artefacto.objects.select_related("media").filter(**filtro).first()
    )

    if artefacto is None:
        raise NotFoundError(detail=f"La capa {capa!r} no existe en esta versión.")

    return url_publica(artefacto.media)  # ty: ignore[invalid-argument-type]


def url_resumen_csv(codigo: str, version: str) -> str:
    artefacto: Artefacto | None = (
        Artefacto.objects
        .select_related("media")
        .filter(corrida=publicada(codigo, version), tipo=TipoArtefacto.RESUMEN_CSV)
        .first()
    )

    if artefacto is None:
        raise NotFoundError(detail="Esta versión no tiene resumen en CSV.")

    return url_publica(artefacto.media)  # ty: ignore[invalid-argument-type]


########################################################################################


def celda_por_codigo(codigo: str, version: str, celda_codigo: str) -> dict:
    corrida: Corrida = publicada(codigo, version)

    posicion: tuple[int, int] | None = corrida.region.grilla().celda_de_codigo(  # ty: ignore[unresolved-attribute]
        celda_codigo
    )

    if posicion is None:
        raise NotFoundError(detail=f"La celda {celda_codigo!r} no está en la grilla.")

    return celda_en(corrida, *posicion)


def celda_por_punto(codigo: str, version: str, lon: float, lat: float) -> dict:
    corrida: Corrida = publicada(codigo, version)

    posicion: tuple[int, int] | None = corrida.region.grilla().celda_de_lonlat(lon, lat)  # ty: ignore[unresolved-attribute]

    if posicion is None:
        raise NotFoundError(detail="El punto está fuera de la grilla de la región.")

    return celda_en(corrida, *posicion)


def celda_en(corrida: Corrida, fila: int, columna: int) -> dict:
    modelo: Celda = Celda.objects.get(
        region_id=corrida.region_id,  # ty: ignore[unresolved-attribute]
        fila=fila,
        columna=columna,
    )

    resultado: ResultadoCelda = ResultadoCelda.objects.get(
        corrida=corrida, celda=modelo
    )

    return celda(resultado, corrida, modelo)


def estanques_de(
    codigo: str, version: str, *, clase: str = "", orden: str = "puntaje"
) -> list[dict]:
    corrida: Corrida = publicada(codigo, version)

    qs = ResultadoEstanque.objects.select_related("estanque").filter(corrida=corrida)

    if clase == "abandonado":
        qs = qs.filter(activo=False)
    elif clase == "activo":
        qs = qs.filter(activo=True)

    qs = qs.order_by(ORDENES_ESTANQUES.get(orden, "-puntaje"), "estanque__numero")

    return [
        {
            "codigo": r.estanque.codigo,
            "geometria": r.estanque.geometria,
            "area_ha": r.area_ha,
            "cv": r.cv,
            "activo": r.activo,
            "dist_canal_km": r.dist_canal_km,
            "if_vecino": r.if_vecino,
            "puntaje": r.puntaje,
        }
        for r in qs
    ]


def descargas(codigo: str, version: str) -> list[dict]:
    corrida: Corrida = publicada(codigo, version)

    return [
        {
            "tipo": a.tipo,
            "formato": a.formato,
            "bytes": a.bytes,
            "sha256": a.sha256,
            "licencia": "CC-BY-4.0",
            "url": url_publica(a.media),
        }
        for a in Artefacto.objects
        .select_related("media")
        .filter(corrida=corrida)
        .exclude(formato=FormatoArtefacto.PNG)
        .order_by("tipo")
    ]


########################################################################################


def perfil_explorado(corrida: Corrida, cambios: dict) -> Perfil:
    base: Perfil = corrida.perfil.a_perfil()  # ty: ignore[unresolved-attribute]

    permitidos: set[str] = {f.name for f in fields(Perfil)}

    return replace(base, **{k: v for k, v in cambios.items() if k in permitidos})


def explorar(codigo: str, version: str, cambios: dict) -> dict:
    corrida: Corrida = publicada(codigo, version)

    perfil: Perfil = perfil_explorado(corrida, cambios)

    huella: str = sha256(f"{corrida.id}:{perfil.huella()}".encode()).hexdigest()

    llave: str = f"mangroove:exploracion:{huella}"

    guardado: dict | None = cache.get(llave)

    if guardado is None:
        guardado = calcular_exploracion(corrida, perfil)

        cache.set(llave, guardado, SEGUNDOS_EXPLORACION)

    return {
        "exploracion": True,
        "huella": huella,
        "version": corrida.version,
        "umbrales": dumps(cambios, sort_keys=True),
        "capas": {
            "desconexion": (
                f"regiones/{codigo}/versiones/{version}/exploraciones/{huella}/capas/desconexion/"
            ),
        },
        "resumen": guardado["resumen"],
    }


def calcular_exploracion(corrida: Corrida, perfil: Perfil) -> dict:
    grilla: Grilla = corrida.region.grilla()  # ty: ignore[unresolved-attribute]

    hh, hv, cambios = cubo_de(corrida)

    fechas: tuple[Fecha, ...] = tuple(
        Fecha(track=f.adquisicion.track, marea_m=f.marea_m, lluvia_3d_mm=f.lluvia_3d_mm)
        for f in corrida.fechas.select_related("adquisicion").order_by("orden")  # ty: ignore[unresolved-attribute]
    )

    resultado: Resultado = analizar(
        pila=Pila(hh=hh, hv=hv, fechas=fechas),
        auxiliares=auxiliares_de(
            (
                ci.insumo
                for ci in corrida.insumos.select_related("insumo", "insumo__region")  # ty: ignore[unresolved-attribute]
            ),
            grilla,
        ),
        grilla=grilla,
        perfil=perfil,
        semilla=corrida.semilla,  # ty: ignore[invalid-argument-type]
        cambios_previos=cambios,
    )

    capa = capa_desconexion(
        codigos_conexion(
            resultado.en_mascara,
            asarray(resultado.frecuencias.datos_suficientes),
            resultado.desconectada,
        ),
        grilla,
    )

    return {
        "png": b64encode(capa.contenido).decode(),
        "resumen": [
            {
                "pais": r.pais,
                "ha_manglar": r.ha_manglar,
                "ha_desconectada": r.ha_desconectada,
                "ha_insuficiente": r.ha_insuficiente,
            }
            for r in resultado.resumen_pais
        ],
    }


def png_exploracion(huella: str) -> bytes:
    guardado: dict | None = cache.get(f"mangroove:exploracion:{huella}")

    if guardado is None:
        raise NotFoundError(detail="La exploración venció o no existe.")

    return b64decode(guardado["png"])

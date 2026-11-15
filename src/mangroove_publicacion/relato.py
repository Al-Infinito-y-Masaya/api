from dataclasses import dataclass
from math import cos, floor, log2, radians
from typing import TYPE_CHECKING

from numpy import argwhere, bincount, full, isfinite, lexsort, nan, ones
from scipy.ndimage import label

from mangroove_analisis.models import Corrida, CorridaFecha, ResultadoCelda
from mangroove_publicacion.contrato import FORMATO
from mangroove_publicacion.enums import TipoArtefacto

if TYPE_CHECKING:
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo, Numeros
    from mangroove_publicacion.services import Matrices
    from mangroove_regiones.models import Region

########################################################################################

METROS_POR_PIXEL_Z0: float = 156_543.03392

PIXELES_VISTA: int = 600

ZOOM_CELDA: int = 16

ZOOM_ESTANQUE: int = 15

########################################################################################


class RelatoError(ValueError):
    def __init__(self, acto: str, motivo: str) -> None:
        super().__init__(f"El acto {acto!r} no tiene datos: {motivo}")


@dataclass(frozen=True, slots=True)
class Grupo:
    filas: Arreglo
    columnas: Arreglo


########################################################################################


def escena(  # ruff: ignore[too-many-arguments]
    identificador: str,
    *,
    capas: list[str],
    centro: tuple[float, float],
    zoom: int,
    fechas: list[str] | None = None,
    celdas: list[str] | None = None,
    datos: dict | None = None,
) -> dict:
    return {
        "id": identificador,
        "capas": capas,
        "fechas": fechas or [],
        "centro": [round(centro[0], 6), round(centro[1], 6)],
        "zoom": zoom,
        "celdas": celdas or [],
        "datos": datos or {},
    }


def zoom_para(extension_m: float, lat: float, minimo: int) -> int:
    resolucion: float = extension_m / PIXELES_VISTA

    zoom: int = floor(log2(METROS_POR_PIXEL_Z0 * cos(radians(lat)) / resolucion))

    return max(minimo, min(ZOOM_CELDA, zoom))


def centro_celdas(
    grilla: Grilla, filas: Numeros, columnas: Numeros
) -> tuple[float, float]:
    este, norte = grilla.centro(filas, columnas)

    lon, lat = grilla.lonlat(float(este.mean()), float(norte.mean()))

    return float(lon), float(lat)


########################################################################################


def lugar(fechas: list[CorridaFecha], region: Region) -> dict:
    if not fechas:
        raise RelatoError("lugar", "la corrida no tiene fechas.")

    elegida: CorridaFecha = max(
        fechas,
        key=lambda f: (f.adquisicion.cobertura, -f.orden),  # ty: ignore[unresolved-attribute, unsupported-operator]
    )

    return escena(
        "lugar",
        capas=[TipoArtefacto.RGB],
        fechas=[elegida.fecha_codigo],  # ty: ignore[invalid-argument-type]
        centro=(region.centro_lon, region.centro_lat),  # ty: ignore[invalid-argument-type]
        zoom=region.zoom_inicial,  # ty: ignore[invalid-argument-type]
        datos={"cobertura": elegida.adquisicion.cobertura},  # ty: ignore[unresolved-attribute]
    )


def ritmo(fechas: list[CorridaFecha], region: Region) -> dict:
    por_track: dict[int, list[CorridaFecha]] = {}

    for f in fechas:
        if f.marea_m is not None:
            por_track.setdefault(f.adquisicion.track, []).append(f)  # ty: ignore[unresolved-attribute]

    pares: list[tuple[CorridaFecha, CorridaFecha]] = [
        (
            min(grupo, key=lambda f: (f.marea_m, f.orden)),
            max(grupo, key=lambda f: (f.marea_m, -f.orden)),  # ty: ignore[unsupported-operator]
        )
        for grupo in por_track.values()
        if len(grupo) > 1
    ]

    pares = [(baja, alta) for baja, alta in pares if alta.marea_m > baja.marea_m]

    if not pares:
        raise RelatoError(
            "ritmo", "ningún track tiene dos fechas con mareas distintas."
        )

    baja, alta = max(pares, key=lambda p: (p[1].marea_m - p[0].marea_m, -p[0].orden))  # ty: ignore[unsupported-operator]

    return escena(
        "ritmo",
        capas=[TipoArtefacto.CLASES],
        fechas=[baja.fecha_codigo, alta.fecha_codigo],  # ty: ignore[invalid-argument-type]
        centro=(region.centro_lon, region.centro_lat),  # ty: ignore[invalid-argument-type]
        zoom=region.zoom_inicial,  # ty: ignore[invalid-argument-type]
        datos={
            "track": baja.adquisicion.track,  # ty: ignore[unresolved-attribute]
            "marea_m": [baja.marea_m, alta.marea_m],
        },
    )


def grupo_mayor(desconectada: Arreglo, grilla: Grilla) -> Grupo:
    etiquetas, n = label(
        desconectada.reshape(grilla.alto, grilla.ancho),
        structure=ones((3, 3), dtype=bool),
    )

    if n == 0:
        raise RelatoError("desconexion", "no hay celdas desconectadas.")

    tamanos: Arreglo = bincount(etiquetas.ravel())

    tamanos[0] = 0

    posiciones: Arreglo = argwhere(etiquetas == int(tamanos.argmax()))

    return Grupo(filas=posiciones[:, 0], columnas=posiciones[:, 1])


def desconexion(grupo: Grupo, grilla: Grilla, region: Region) -> dict:
    centro: tuple[float, float] = centro_celdas(grilla, grupo.filas, grupo.columnas)

    extension: float = (
        max(
            int(grupo.filas.max() - grupo.filas.min()),
            int(grupo.columnas.max() - grupo.columnas.min()),
        )
        + 4
    ) * grilla.celda_m

    return escena(
        "desconexion",
        capas=[TipoArtefacto.IF_ALTA, TipoArtefacto.DESCONEXION],
        centro=centro,
        zoom=zoom_para(extension, centro[1], region.zoom_inicial),  # ty: ignore[invalid-argument-type]
        datos={
            "n_celdas": len(grupo.filas),
            "ha": round(len(grupo.filas) * grilla.hectareas_por_celda, 2),
        },
    )


def confianzas(corrida: Corrida, grilla: Grilla) -> Arreglo:
    valores: Arreglo = full(grilla.n, nan)

    for fila, columna, confianza in ResultadoCelda.objects.filter(
        corrida=corrida, cambio_orden__isnull=False
    ).values_list("celda__fila", "celda__columna", "cambio_confianza"):
        valores[fila * grilla.ancho + columna] = confianza

    return valores


def parche(
    grupo: Grupo, m: Matrices, confianza: Arreglo, grilla: Grilla
) -> tuple[dict, int]:
    indices: Arreglo = grupo.filas * grilla.ancho + grupo.columnas

    validos: Arreglo = indices[m.suficientes[indices] & isfinite(m.if_alta[indices])]

    if validos.size == 0:
        raise RelatoError("parche", "el grupo no tiene celdas con datos suficientes.")

    con_cambio: Arreglo = validos[isfinite(confianza[validos])]

    candidatos: Arreglo = con_cambio if con_cambio.size else validos

    sin_confianza: Arreglo = full(candidatos.size, 0.0)

    if con_cambio.size:
        sin_confianza = -confianza[candidatos]

    elegido: int = int(
        candidatos[lexsort((candidatos, sin_confianza, m.if_alta[candidatos]))[0]]
    )

    fila, columna = divmod(elegido, grilla.ancho)

    lon, lat = centro_celdas(grilla, fila, columna)

    return (
        escena(
            "parche",
            capas=[TipoArtefacto.DESCONEXION],
            centro=(lon, lat),
            zoom=ZOOM_CELDA,
            celdas=[grilla.codigo(fila, columna)],
            datos={
                "if_alta": round(float(m.if_alta[elegido]), 4),
                "cambio": bool(con_cambio.size),
            },
        ),
        elegido,
    )


def restauracion(corrida: Corrida) -> dict | None:
    mejor = (
        corrida.estanques  # ty: ignore[unresolved-attribute]
        .select_related("estanque")
        .filter(activo=False)
        .order_by("-puntaje", "estanque__numero")
        .first()
    )

    if mejor is None:
        return None

    anillo: list = mejor.estanque.geometria["coordinates"][0]

    if mejor.estanque.geometria["type"] == "MultiPolygon":
        anillo = anillo[0]

    return escena(
        "restauracion",
        capas=[TipoArtefacto.ESTANQUES],
        centro=(
            sum(p[0] for p in anillo) / len(anillo),
            sum(p[1] for p in anillo) / len(anillo),
        ),
        zoom=ZOOM_ESTANQUE,
        datos={
            "estanque": mejor.estanque.codigo,
            "puntaje": mejor.puntaje,
            "area_ha": mejor.area_ha,
        },
    )


def incertidumbre(m: Matrices, elegido: int, anterior: dict, grilla: Grilla) -> dict:
    if not isfinite(m.p_error).any():
        raise RelatoError("incertidumbre", "la capa p_error está vacía.")

    fila, columna = divmod(elegido, grilla.ancho)

    return escena(
        "incertidumbre",
        capas=[TipoArtefacto.P_ERROR],
        centro=tuple(anterior["centro"]),
        zoom=anterior["zoom"],
        celdas=[grilla.codigo(fila, columna)],
        datos={
            "p_error": (
                round(float(m.p_error[elegido]), 4)
                if isfinite(m.p_error[elegido])
                else None
            ),
        },
    )


########################################################################################


def relato(corrida: Corrida, m: Matrices) -> dict:
    region: Region = corrida.region  # ty: ignore[invalid-assignment]
    grilla: Grilla = region.grilla()

    fechas: list[CorridaFecha] = list(
        corrida.fechas.select_related("adquisicion").order_by("orden")  # ty: ignore[unresolved-attribute]
    )

    escenas: list[dict] = [lugar(fechas, region), ritmo(fechas, region)]

    grupo: Grupo = grupo_mayor(m.desconectada, grilla)

    escenas.append(desconexion(grupo, grilla, region))

    escena_parche, elegido = parche(grupo, m, confianzas(corrida, grilla), grilla)

    escenas.append(escena_parche)

    final: dict | None = restauracion(corrida)

    escenas.append(
        final if final is not None else incertidumbre(m, elegido, escenas[2], grilla)
    )

    return {
        "formato": FORMATO,
        "region": region.codigo,
        "version": corrida.version,
        "escenas": escenas,
    }

from typing import TYPE_CHECKING

from numpy import (
    arctan,
    asarray,
    degrees,
    float32,
    full,
    gradient,
    hypot,
    isfinite,
    nan,
    nan_to_num,
    ones,
    uint8,
    zeros,
)
from rasterio import (
    band,
    open as abrir_raster,
)
from rasterio.features import rasterize
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject, transform_geom

from mangroove_motor.grilla import WGS84, Grilla

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from mangroove_motor.types import Arreglo

########################################################################################

FRACCION_MANGLAR: float = 0.5

########################################################################################


def transformacion(grilla: Grilla) -> Affine:
    return from_origin(grilla.x0, grilla.y0, grilla.celda_m, grilla.celda_m)


def rasterizar_geometrias(
    formas: Iterable[tuple[dict, int]],
    grilla: Grilla,
    *,
    tocadas: bool = True,
    dtype: str = "uint8",
) -> Arreglo:
    proyectadas: list[tuple[dict, int]] = [
        (transform_geom(WGS84, grilla.crs, geometria), valor)
        for geometria, valor in formas
    ]

    if not proyectadas:
        return zeros(grilla.n, dtype=dtype)

    return rasterize(
        proyectadas,
        all_touched=tocadas,
        dtype=dtype,
        fill=0,
        out_shape=(grilla.alto, grilla.ancho),
        transform=transformacion(grilla),
    ).reshape(grilla.n)


def rasterizar_poligono(geometria: dict, grilla: Grilla) -> Arreglo:
    return rasterizar_geometrias([(geometria, 1)], grilla, tocadas=False).astype(bool)


def geometrias_geojson(objeto: dict) -> list[tuple[dict, dict]]:
    if objeto.get("type") == "FeatureCollection":
        caracteristicas: list[dict] = objeto["features"]
    elif objeto.get("type") == "Feature":
        caracteristicas = [objeto]
    else:
        caracteristicas = [{"geometry": objeto, "properties": {}}]

    return [
        (c["geometry"], c.get("properties") or {})
        for c in caracteristicas
        if c.get("geometry")
    ]


def reproyectar_raster(
    ruta: Path,
    grilla: Grilla,
    *,
    remuestreo: Resampling = Resampling.average,
) -> Arreglo:
    destino: Arreglo = full((grilla.alto, grilla.ancho), nan, dtype=float32)

    with abrir_raster(ruta) as fuente:
        reproject(
            destination=destino,
            dst_crs=grilla.crs,
            dst_nodata=nan,
            dst_transform=transformacion(grilla),
            resampling=remuestreo,
            source=band(fuente, 1),
        )

    return destino.reshape(grilla.n)


def cobertura_raster(valores: Arreglo) -> float:
    datos: Arreglo = asarray(valores)

    return float(isfinite(datos).sum()) / max(1, datos.size)


########################################################################################


def mascara_manglar_raster(fraccion: Arreglo) -> Arreglo:
    return nan_to_num(asarray(fraccion, dtype=float32), nan=0.0) >= FRACCION_MANGLAR


def barreras_desde_geojson(objeto: dict, grilla: Grilla) -> Arreglo:
    formas: list[tuple[dict, int]] = []

    for geometria, propiedades in geometrias_geojson(objeto):
        tipo: str = str(
            propiedades.get("tipo", propiedades.get("type", "borda"))
        ).lower()

        formas.append((geometria, 2 if ("camino" in tipo or "road" in tipo) else 1))

    return rasterizar_geometrias(formas, grilla)


def paises_desde_geojson(
    objeto: dict, grilla: Grilla
) -> tuple[Arreglo, tuple[str, ...]]:
    codigos: list[str] = []
    formas: list[tuple[dict, int]] = []

    for geometria, propiedades in geometrias_geojson(objeto):
        codigo: str = str(propiedades.get("iso", "")).upper()

        if not codigo:
            continue

        if codigo not in codigos:
            codigos.append(codigo)

        formas.append((geometria, codigos.index(codigo) + 1))

    return rasterizar_geometrias(formas, grilla, tocadas=False), tuple(codigos)


def estanques_desde_geojson(
    objeto: dict,
    grilla: Grilla,
) -> tuple[Arreglo, list[tuple[str, dict]]]:
    formas: list[tuple[dict, int]] = []
    poligonos: list[tuple[str, dict]] = []

    for numero, (geometria, propiedades) in enumerate(geometrias_geojson(objeto), 1):
        codigo: str = str(propiedades.get("id", numero))

        formas.append((geometria, numero))
        poligonos.append((codigo, geometria))

    return rasterizar_geometrias(
        formas, grilla, tocadas=False, dtype="int32"
    ), poligonos


########################################################################################


def pendiente_grados(elevacion: Arreglo, grilla: Grilla) -> Arreglo:
    plano: Arreglo = nan_to_num(
        asarray(elevacion, dtype=float32).reshape(grilla.alto, grilla.ancho),
        nan=0.0,
    )

    gy, gx = gradient(plano, grilla.celda_m)

    return degrees(arctan(hypot(gx, gy))).reshape(grilla.n)


def mascara_humedal(
    grilla: Grilla,
    *,
    elevacion: Arreglo | None,
    exclusion: Arreglo | None,
    pendiente_max: float,
    cota_max: float,
) -> Arreglo:
    humedal: Arreglo = ones(grilla.n, dtype=bool)

    if elevacion is not None:
        cotas: Arreglo = asarray(elevacion, dtype=float32)

        humedal &= ~(
            (pendiente_grados(cotas, grilla) > pendiente_max)
            | (nan_to_num(cotas, nan=0.0) > cota_max)
        )

    if exclusion is not None:
        humedal &= ~asarray(exclusion, dtype=bool)

    return humedal


def codigos_a_indices(codigos: Sequence[str], indices: Arreglo) -> list[str]:
    tabla: list[str] = ["", *codigos]

    return [tabla[int(i)] for i in asarray(indices, dtype=uint8)]

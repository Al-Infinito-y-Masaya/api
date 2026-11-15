from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image
from numpy import (
    arange,
    asarray,
    clip,
    float32,
    full,
    isfinite,
    meshgrid,
    nan,
    nan_to_num,
    round as np_round,
    stack,
    uint8,
    zeros,
)
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.warp import Resampling, calculate_default_transform, reproject

from mangroove_motor.auxiliares import transformacion
from mangroove_motor.grilla import WGS84, Grilla
from mangroove_motor.perfil import Clase

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from mangroove_motor.types import Arreglo

########################################################################################

WEB_MERCATOR: str = "EPSG:3857"

SIN_DATO: int = 255

PASO_TRAMA: int = 4

RANGO_HH: tuple[float, float] = (-25.0, 0.0)
RANGO_HV: tuple[float, float] = (-30.0, -5.0)
RANGO_RAZON: tuple[float, float] = (0.0, 15.0)
RANGO_CAMBIO: tuple[float, float] = (-6.0, 0.0)

AZULES: tuple[str, ...] = (
    "#0d366b",
    "#184f95",
    "#256abf",
    "#3987e5",
    "#6da7ec",
    "#9ec5f4",
    "#cde2fb",
)
NARANJAS: tuple[str, ...] = (
    "#3d1606",
    "#7f3010",
    "#c94f1d",
    "#e57745",
    "#ee9a72",
    "#f5bfa3",
    "#fbe2d4",
)

COLORES_CLASES: dict[Clase, str] = {
    Clase.NI: "#5c5b57",
    Clase.IV: "#199e70",
    Clase.OW: "#3987e5",
    Clase.NC: "#d95926",
}


class Conexion(StrEnum):
    CONECTADA = "conectada"
    DESCONECTADA = "desconectada"
    INSUFICIENTE = "insuficiente"


CODIGOS_CONEXION: dict[Conexion, int] = {
    Conexion.CONECTADA: 0,
    Conexion.DESCONECTADA: 1,
    Conexion.INSUFICIENTE: 2,
}

COLORES_CONEXION: dict[Conexion, str] = {
    Conexion.CONECTADA: "#2f5f50",
    Conexion.DESCONECTADA: "#d95926",
    Conexion.INSUFICIENTE: "#9a9893",
}

########################################################################################


@dataclass(frozen=True, slots=True)
class Capa:
    contenido: bytes
    sha256: str
    limites: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class Lienzo:
    transformacion: object
    ancho: int
    alto: int
    limites: tuple[float, float, float, float]


########################################################################################


def hex_a_rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def rampa(colores: Sequence[str]) -> Callable[[Arreglo], Arreglo]:
    tabla: Arreglo = asarray([hex_a_rgb(c) for c in colores], dtype=float32)

    def aplicar(valores: Arreglo) -> Arreglo:
        t: Arreglo = clip(nan_to_num(valores, nan=0.0), 0.0, 1.0) * (len(colores) - 1)

        k: Arreglo = clip(t.astype(int), 0, len(colores) - 2)

        f: Arreglo = (t - k)[..., None]

        return tabla[k] + (tabla[k + 1] - tabla[k]) * f

    return aplicar


def escalar(valores: Arreglo, rango: tuple[float, float]) -> Arreglo:
    return (asarray(valores, dtype=float32) - rango[0]) / (rango[1] - rango[0])


########################################################################################


def lienzo(grilla: Grilla) -> Lienzo:
    oeste, sur, este, norte = grilla.limites()

    destino, ancho, alto = calculate_default_transform(
        grilla.crs,
        WEB_MERCATOR,
        grilla.ancho,
        grilla.alto,
        left=oeste,
        bottom=sur,
        right=este,
        top=norte,
    )

    x_min, y_max = destino @ (0, 0)
    x_max, y_min = destino @ (ancho, alto)

    lon_min, lat_min = Transformer.from_crs(
        WEB_MERCATOR, WGS84, always_xy=True
    ).transform(
        x_min,
        y_min,
    )
    lon_max, lat_max = Transformer.from_crs(
        WEB_MERCATOR, WGS84, always_xy=True
    ).transform(
        x_max,
        y_max,
    )

    return Lienzo(
        transformacion=destino,
        ancho=int(ancho),
        alto=int(alto),
        limites=(
            round(lon_min, 7),
            round(lat_min, 7),
            round(lon_max, 7),
            round(lat_max, 7),
        ),
    )


def a_mercator(
    valores: Arreglo, grilla: Grilla, destino: Lienzo, *, codigos: bool
) -> Arreglo:
    plano: Arreglo = asarray(valores).reshape(grilla.alto, grilla.ancho)

    if codigos:
        salida: Arreglo = full((destino.alto, destino.ancho), SIN_DATO, dtype=uint8)
        fuente: Arreglo = plano.astype(uint8)
        nodata: float = SIN_DATO
    else:
        salida = full((destino.alto, destino.ancho), nan, dtype=float32)
        fuente = plano.astype(float32)
        nodata = nan

    reproject(
        destination=salida,
        dst_crs=WEB_MERCATOR,
        dst_nodata=nodata,
        dst_transform=destino.transformacion,
        resampling=Resampling.nearest,
        source=fuente,
        src_crs=grilla.crs,
        src_nodata=nodata,
        src_transform=transformacion(grilla),
    )

    return salida


def trama(alto: int, ancho: int) -> Arreglo:
    xs, ys = meshgrid(arange(ancho), arange(alto))

    return (xs + ys) % PASO_TRAMA == 0


def a_png(rgba: Arreglo, destino: Lienzo) -> Capa:
    buffer: BytesIO = BytesIO()

    Image.fromarray(asarray(np_round(rgba), dtype=uint8), mode="RGBA").save(
        buffer,
        format="PNG",
        optimize=True,
    )

    contenido: bytes = buffer.getvalue()

    return Capa(
        contenido=contenido,
        sha256=sha256(contenido).hexdigest(),
        limites=destino.limites,
    )


def rgba_vacio(destino: Lienzo) -> Arreglo:
    return zeros((destino.alto, destino.ancho, 4), dtype=float32)


########################################################################################


def capa_rgb(hh: Arreglo, hv: Arreglo, grilla: Grilla) -> Capa:
    destino: Lienzo = lienzo(grilla)

    h: Arreglo = a_mercator(hh, grilla, destino, codigos=False)
    v: Arreglo = a_mercator(hv, grilla, destino, codigos=False)

    rgba: Arreglo = rgba_vacio(destino)

    rgba[..., :3] = 255 * clip(
        stack(
            [escalar(h, RANGO_HH), escalar(v, RANGO_HV), escalar(h - v, RANGO_RAZON)],
            axis=-1,
        ),
        0.0,
        1.0,
    )
    rgba[..., 3] = 255 * (isfinite(h) & isfinite(v))
    rgba[..., :3] = nan_to_num(rgba[..., :3], nan=0.0)

    return a_png(rgba, destino)


def capa_categorica(codigos: Arreglo, colores: dict[int, str], grilla: Grilla) -> Capa:
    destino: Lienzo = lienzo(grilla)

    valores: Arreglo = a_mercator(codigos, grilla, destino, codigos=True)

    rgba: Arreglo = rgba_vacio(destino)

    for codigo, color in colores.items():
        celdas: Arreglo = valores == codigo

        rgba[celdas, :3] = hex_a_rgb(color)
        rgba[celdas, 3] = 255

    return a_png(rgba, destino)


def capa_clases(clases: Arreglo, grilla: Grilla) -> Capa:
    return capa_categorica(
        clases,
        {int(clase): color for clase, color in COLORES_CLASES.items()},
        grilla,
    )


def capa_continua(
    valores: Arreglo,
    grilla: Grilla,
    *,
    colores: Sequence[str],
    rango: tuple[float, float] = (0.0, 1.0),
    tramada: Arreglo | None = None,
) -> Capa:
    destino: Lienzo = lienzo(grilla)

    datos: Arreglo = a_mercator(valores, grilla, destino, codigos=False)

    rgba: Arreglo = rgba_vacio(destino)

    hay: Arreglo = isfinite(datos)

    rgba[..., :3] = rampa(colores)(escalar(datos, rango))
    rgba[..., 3] = 255 * hay

    if tramada is not None:
        marcas: Arreglo = (
            a_mercator(tramada.astype(uint8), grilla, destino, codigos=True) == 1
        )

        rgba[marcas, :3] = hex_a_rgb(COLORES_CONEXION[Conexion.INSUFICIENTE])
        rgba[marcas & trama(destino.alto, destino.ancho), :3] = 40
        rgba[marcas, 3] = 255

    return a_png(rgba, destino)


def codigos_conexion(
    en_mascara: Arreglo, suficientes: Arreglo, desconectada: Arreglo
) -> Arreglo:
    codigos: Arreglo = full(asarray(en_mascara).shape, SIN_DATO, dtype=uint8)

    codigos[en_mascara & suficientes] = CODIGOS_CONEXION[Conexion.CONECTADA]
    codigos[en_mascara & suficientes & desconectada] = CODIGOS_CONEXION[
        Conexion.DESCONECTADA
    ]
    codigos[en_mascara & ~suficientes] = CODIGOS_CONEXION[Conexion.INSUFICIENTE]

    return codigos


def capa_desconexion(codigos: Arreglo, grilla: Grilla) -> Capa:
    destino: Lienzo = lienzo(grilla)

    valores: Arreglo = a_mercator(codigos, grilla, destino, codigos=True)

    rgba: Arreglo = rgba_vacio(destino)

    for conexion, codigo in CODIGOS_CONEXION.items():
        celdas: Arreglo = valores == codigo

        rgba[celdas, :3] = hex_a_rgb(COLORES_CONEXION[conexion])
        rgba[celdas, 3] = 255

    insuficientes: Arreglo = valores == CODIGOS_CONEXION[Conexion.INSUFICIENTE]

    rgba[insuficientes & trama(destino.alto, destino.ancho), :3] = 40

    return a_png(rgba, destino)


########################################################################################


def geotiff(valores: Arreglo, grilla: Grilla, *, entero: bool = False) -> bytes:
    plano: Arreglo = asarray(valores).reshape(grilla.alto, grilla.ancho)

    perfil: dict = {
        "count": 1,
        "crs": grilla.crs,
        "driver": "COG",
        "height": grilla.alto,
        "transform": transformacion(grilla),
        "width": grilla.ancho,
    }

    if entero:
        perfil |= {"dtype": "uint8", "nodata": SIN_DATO}
        datos: Arreglo = plano.astype(uint8)
    else:
        perfil |= {"dtype": "float32", "nodata": nan}
        datos = plano.astype(float32)

    with MemoryFile() as memoria:
        with memoria.open(**perfil) as salida:
            salida.write(datos, 1)

        return memoria.read()


def leyendas() -> dict[str, list[dict[str, str]]]:
    return {
        "clases": [
            {"codigo": clase.name, "color": color}
            for clase, color in COLORES_CLASES.items()
        ],
        "desconexion": [
            {"codigo": conexion.value, "color": color}
            for conexion, color in COLORES_CONEXION.items()
        ],
        "if": [
            {"codigo": "0", "color": AZULES[-1]},
            {"codigo": "1", "color": AZULES[0]},
        ],
        "if_alta": [
            {"codigo": "0", "color": AZULES[-1]},
            {"codigo": "1", "color": AZULES[0]},
        ],
        "p_error": [
            {"codigo": "0", "color": NARANJAS[-1]},
            {"codigo": "1", "color": NARANJAS[0]},
        ],
        "cambio": [
            {"codigo": str(RANGO_CAMBIO[0]), "color": NARANJAS[0]},
            {"codigo": str(RANGO_CAMBIO[1]), "color": NARANJAS[-1]},
        ],
    }

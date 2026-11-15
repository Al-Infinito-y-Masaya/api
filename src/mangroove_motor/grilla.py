from dataclasses import dataclass
from functools import cached_property
from json import loads
from math import ceil, floor
from re import IGNORECASE, findall, match
from typing import TYPE_CHECKING

from numpy import (
    asarray,
    floor as np_floor,
    int64,
)
from pyproj import Transformer

if TYPE_CHECKING:
    from mangroove_motor.types import Arreglo, Caja, CoordenadasLonLat, Numeros

########################################################################################

WGS84: str = "EPSG:4326"

NUMERO: str = r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?"

PARTES_CODIGO: int = 3

VERTICES_MINIMOS: int = 4

LON_MAXIMA: float = 180.0

LAT_MAXIMA: float = 90.0

########################################################################################


class AoiInvalidaError(ValueError):
    pass


########################################################################################


@dataclass(frozen=True, slots=True)
class Aoi:
    wkt: str
    anillo: tuple[CoordenadasLonLat, ...]

    @property
    def caja(self) -> Caja:
        lons: list[float] = [p[0] for p in self.anillo]
        lats: list[float] = [p[1] for p in self.anillo]

        return (min(lons), min(lats), max(lons), max(lats))

    @property
    def centroide(self) -> CoordenadasLonLat:
        oeste, sur, este, norte = self.caja

        return ((oeste + este) / 2, (sur + norte) / 2)

    @property
    def geojson(self) -> dict:
        return {"coordinates": [[list(p) for p in self.anillo]], "type": "Polygon"}


########################################################################################


@dataclass(frozen=True, kw_only=True)
class Grilla:
    epsg: int
    x0: float
    y0: float
    celda_m: float
    ancho: int
    alto: int

    @property
    def n(self) -> int:
        return self.ancho * self.alto

    @property
    def crs(self) -> str:
        return f"EPSG:{self.epsg}"

    @property
    def hectareas_por_celda(self) -> float:
        return self.celda_m * self.celda_m / 10_000

    @cached_property
    def a_lonlat(self) -> Transformer:
        return Transformer.from_crs(self.crs, WGS84, always_xy=True)

    @cached_property
    def desde_lonlat(self) -> Transformer:
        return Transformer.from_crs(WGS84, self.crs, always_xy=True)

    def centro(self, fila: Numeros, columna: Numeros) -> tuple[Arreglo, Arreglo]:
        este: Arreglo = self.x0 + (asarray(columna) + 0.5) * self.celda_m
        norte: Arreglo = self.y0 - (asarray(fila) + 0.5) * self.celda_m

        return este, norte

    def indice(self, este: Numeros, norte: Numeros) -> tuple[Arreglo, Arreglo]:
        columna: Arreglo = np_floor((asarray(este) - self.x0) / self.celda_m)
        fila: Arreglo = np_floor((self.y0 - asarray(norte)) / self.celda_m)

        return fila.astype(int64), columna.astype(int64)

    def celda_de_lonlat(self, lon: float, lat: float) -> tuple[int, int] | None:
        este, norte = self.desde_lonlat.transform(lon, lat)

        fila, columna = self.indice(este, norte)

        if not (0 <= int(fila) < self.alto and 0 <= int(columna) < self.ancho):
            return None

        return int(fila), int(columna)

    def codigo(self, fila: int, columna: int) -> str:
        este, norte = self.centro(fila, columna)

        return f"c_{round(float(este))}_{round(float(norte))}"

    def celda_de_codigo(self, codigo: str) -> tuple[int, int] | None:
        partes: list[str] = codigo.split("_")

        if len(partes) != PARTES_CODIGO or partes[0] != "c":
            return None

        try:
            este, norte = float(partes[1]), float(partes[2])
        except ValueError:
            return None

        fila, columna = self.indice(este, norte)

        if not (0 <= int(fila) < self.alto and 0 <= int(columna) < self.ancho):
            return None

        if self.codigo(int(fila), int(columna)) != codigo:
            return None

        return int(fila), int(columna)

    def lonlat(self, este: Numeros, norte: Numeros) -> tuple[Arreglo, Arreglo]:
        lon, lat = self.a_lonlat.transform(este, norte)

        return asarray(lon), asarray(lat)

    def limites(self) -> tuple[float, float, float, float]:
        return (
            self.x0,
            self.y0 - self.alto * self.celda_m,
            self.x0 + self.ancho * self.celda_m,
            self.y0,
        )


########################################################################################


def zona_utm(lon: float, lat: float) -> int:
    zona: int = min(60, max(1, floor((lon + 180) / 6) + 1))

    return (32600 if lat >= 0 else 32700) + zona


def grilla_desde_caja(
    caja: Caja,
    *,
    celda_m: float,
    epsg: int | None = None,
) -> Grilla:
    oeste, sur, este, norte = caja

    destino: int = epsg or zona_utm((oeste + este) / 2, (sur + norte) / 2)

    transformador: Transformer = Transformer.from_crs(
        WGS84,
        f"EPSG:{destino}",
        always_xy=True,
    )

    xs, ys = transformador.transform(
        [oeste, este, oeste, este],
        [sur, sur, norte, norte],
    )

    x0: float = floor(min(xs) / celda_m) * celda_m
    y0: float = ceil(max(ys) / celda_m) * celda_m

    return Grilla(
        epsg=destino,
        x0=x0,
        y0=y0,
        celda_m=celda_m,
        ancho=ceil((max(xs) - x0) / celda_m),
        alto=ceil((y0 - min(ys)) / celda_m),
    )


########################################################################################


def parsear_aoi(texto: str) -> Aoi:
    contenido: str = texto.strip()

    if contenido.startswith("{"):
        anillo: list[CoordenadasLonLat] = anillo_geojson(loads(contenido))
    elif match(r"^\s*(MULTI)?POLYGON", contenido, IGNORECASE):
        anillo = [
            (float(x), float(y))
            for x, y in (
                par.split() for par in findall(rf"{NUMERO}\s+{NUMERO}", contenido)
            )
        ]
    else:
        raise AoiInvalidaError("El área no es un POLYGON en WKT ni un GeoJSON.")

    if len(anillo) < VERTICES_MINIMOS:
        raise AoiInvalidaError("El polígono necesita al menos cuatro vértices.")

    if anillo[0] != anillo[-1]:
        anillo.append(anillo[0])

    aoi: Aoi = Aoi(
        wkt="POLYGON((" + ",".join(f"{x} {y}" for x, y in anillo) + "))",
        anillo=tuple(anillo),
    )

    oeste, sur, este, norte = aoi.caja

    if not (
        -LON_MAXIMA <= oeste < este <= LON_MAXIMA
        and -LAT_MAXIMA <= sur < norte <= LAT_MAXIMA
    ):
        raise AoiInvalidaError(
            "El área está fuera de rango o tiene longitud y latitud invertidas.",
        )

    return aoi


def anillo_geojson(objeto: dict) -> list[CoordenadasLonLat]:
    if objeto.get("type") == "FeatureCollection":
        objeto = objeto["features"][0]

    geometria: dict = objeto.get("geometry", objeto)

    if geometria.get("type") == "Polygon":
        anillo: list = geometria["coordinates"][0]
    elif geometria.get("type") == "MultiPolygon":
        anillo = geometria["coordinates"][0][0]
    else:
        raise AoiInvalidaError("El GeoJSON no contiene un polígono.")

    return [(float(p[0]), float(p[1])) for p in anillo]

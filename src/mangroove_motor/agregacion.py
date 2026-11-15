from dataclasses import dataclass
from typing import TYPE_CHECKING

from numpy import (
    asarray,
    bincount,
    broadcast_to,
    errstate,
    float32,
    float64,
    floor,
    full,
    int64,
    isfinite,
    log10,
    maximum,
    meshgrid,
    nan,
    power,
    stack,
)
from pyproj import Transformer

if TYPE_CHECKING:
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo

########################################################################################

MINIMO_LINEAL: float = 1e-12

MASCARA_RELLENO: int = 255

########################################################################################


@dataclass(frozen=True, slots=True)
class Suma:
    total: Arreglo
    conteo: Arreglo

    def __add__(self, otra: Suma) -> Suma:
        return Suma(total=self.total + otra.total, conteo=self.conteo + otra.conteo)

    def media(self) -> Arreglo:
        salida: Arreglo = full(self.total.shape, nan, dtype=float64)

        hay: Arreglo = self.conteo > 0

        salida[hay] = self.total[hay] / self.conteo[hay]

        return salida


@dataclass(frozen=True, slots=True)
class Agregado:
    hh: Suma
    hv: Suma

    def __add__(self, otro: Agregado) -> Agregado:
        return Agregado(hh=self.hh + otro.hh, hv=self.hv + otro.hv)

    def en_db(self) -> Arreglo:
        return stack([a_db(self.hh.media()), a_db(self.hv.media())]).astype(float32)


########################################################################################


def a_db(lineal: Arreglo) -> Arreglo:
    valores: Arreglo = asarray(lineal, dtype=float64)

    with errstate(divide="ignore", invalid="ignore"):
        return 10 * log10(maximum(valores, MINIMO_LINEAL))


def a_lineal(db: Arreglo) -> Arreglo:
    return power(10.0, asarray(db, dtype=float64) / 10)


def muestras_validas(mascara: Arreglo, *, estricta: bool) -> Arreglo:
    valores: Arreglo = asarray(mascara)

    if estricta:
        return (valores > 0) & (valores < MASCARA_RELLENO)

    return valores < MASCARA_RELLENO


########################################################################################


def indices_en_grilla(
    xs: Arreglo,
    ys: Arreglo,
    epsg: int,
    grilla: Grilla,
) -> tuple[Arreglo, Arreglo]:
    if epsg == grilla.epsg:
        columnas: Arreglo = floor((asarray(xs) - grilla.x0) / grilla.celda_m)
        filas: Arreglo = floor((grilla.y0 - asarray(ys)) / grilla.celda_m)

        return filas.astype(int64)[:, None], columnas.astype(int64)[None, :]

    malla_x, malla_y = meshgrid(xs, ys)

    transformador: Transformer = Transformer.from_crs(
        f"EPSG:{epsg}",
        grilla.crs,
        always_xy=True,
    )

    este, norte = transformador.transform(malla_x, malla_y)

    return grilla.indice(este, norte)


def sumar_bloque(
    bloque: Arreglo,
    filas: Arreglo,
    columnas: Arreglo,
    grilla: Grilla,
    validas: Arreglo | None = None,
) -> Suma:
    valores: Arreglo = asarray(bloque, dtype=float64)

    filas_b: Arreglo = broadcast_to(filas, valores.shape)
    columnas_b: Arreglo = broadcast_to(columnas, valores.shape)

    ok: Arreglo = (
        isfinite(valores)
        & (valores > 0)
        & (filas_b >= 0)
        & (columnas_b >= 0)
        & (filas_b < grilla.alto)
        & (columnas_b < grilla.ancho)
    )

    if validas is not None:
        ok &= asarray(validas, dtype=bool)

    lineales: Arreglo = filas_b[ok] * grilla.ancho + columnas_b[ok]

    return Suma(
        total=bincount(lineales, weights=valores[ok], minlength=grilla.n).astype(
            float64,
        ),
        conteo=bincount(lineales, minlength=grilla.n).astype(int64),
    )


def agregar(  # ruff: ignore[too-many-arguments]
    *,
    hh: Arreglo,
    hv: Arreglo,
    xs: Arreglo,
    ys: Arreglo,
    epsg: int,
    grilla: Grilla,
    mascara: Arreglo | None = None,
    estricta: bool = True,
) -> Agregado:
    filas, columnas = indices_en_grilla(xs, ys, epsg, grilla)

    validas: Arreglo | None = (
        None if mascara is None else muestras_validas(mascara, estricta=estricta)
    )

    return Agregado(
        hh=sumar_bloque(hh, filas, columnas, grilla, validas),
        hv=sumar_bloque(hv, filas, columnas, grilla, validas),
    )


def cobertura(grilla_db: Arreglo, dentro: Arreglo) -> float:
    adentro: Arreglo = asarray(dentro, dtype=bool)

    total: int = int(adentro.sum())

    if total == 0:
        return 0.0

    validas: Arreglo = isfinite(grilla_db[0]) & isfinite(grilla_db[1]) & adentro

    return float(validas.sum()) / total

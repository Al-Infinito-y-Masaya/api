from dataclasses import dataclass
from typing import TYPE_CHECKING

from numpy import (
    abs as np_abs,
    arange,
    argmax,
    asarray,
    cumsum,
    float64,
    full,
    int16,
    isfinite,
    maximum,
    minimum,
    nan,
    packbits,
    stack,
    unique,
    where,
    zeros,
)
from numpy.random import default_rng

if TYPE_CHECKING:
    from mangroove_motor.perfil import Perfil
    from mangroove_motor.types import Arreglo

########################################################################################

FECHAS_MINIMAS: int = 4

BLOQUE_CELDAS: int = 2_000

SIN_CAMBIO: int = -1

########################################################################################


@dataclass(frozen=True, slots=True)
class Cambios:
    orden: Arreglo
    confianza: Arreglo
    delta_hv_db: Arreglo
    significativo: Arreglo


########################################################################################


def anomalias(hv: Arreglo, media_hv_por_fecha: Arreglo) -> Arreglo:
    return asarray(hv, dtype=float64) - asarray(media_hv_por_fecha, dtype=float64)


def permutaciones(k: int, b: int, semilla: int) -> Arreglo:
    generador = default_rng([semilla, k])

    return stack([generador.permutation(k) for _ in range(b)])


def rango_cusum(series: Arreglo) -> tuple[Arreglo, Arreglo]:
    acumulada: Arreglo = cumsum(series, axis=-1)

    rango: Arreglo = maximum(acumulada.max(axis=-1), 0.0) - minimum(
        acumulada.min(axis=-1),
        0.0,
    )

    return rango, argmax(np_abs(acumulada), axis=-1)


def cusum_bloque(  # ruff: ignore[too-many-locals]
    series: Arreglo,
    perms: Arreglo,
) -> tuple[Arreglo, Arreglo, Arreglo]:
    centradas: Arreglo = series - series.mean(axis=1, keepdims=True)

    observado, posicion = rango_cusum(centradas)

    barajadas: Arreglo = centradas[:, perms]

    rangos, _ = rango_cusum(barajadas)

    confianza: Arreglo = (rangos < observado[:, None]).mean(axis=1)

    k: int = series.shape[1]

    corte: Arreglo = minimum(posicion + 1, k - 1)

    indices: Arreglo = arange(k)[None, :]

    antes: Arreglo = indices < corte[:, None]

    suma_antes: Arreglo = where(antes, series, 0.0).sum(axis=1)
    suma_despues: Arreglo = where(~antes, series, 0.0).sum(axis=1)

    n_antes: Arreglo = antes.sum(axis=1)
    n_despues: Arreglo = k - n_antes

    delta: Arreglo = suma_despues / maximum(n_despues, 1) - suma_antes / maximum(
        n_antes,
        1,
    )

    return corte, confianza, delta


def detectar_cambios(  # ruff: ignore[too-many-locals]
    series_hv: Arreglo,
    elegibles: Arreglo,
    perfil: Perfil,
    semilla: int,
) -> Cambios:
    datos: Arreglo = asarray(series_hv, dtype=float64)

    t, n = datos.shape

    orden: Arreglo = full(n, SIN_CAMBIO, dtype=int16)
    confianza: Arreglo = full(n, nan, dtype=float64)
    delta: Arreglo = full(n, nan, dtype=float64)

    disponibles: Arreglo = isfinite(datos)

    celdas: Arreglo = where(asarray(elegibles, dtype=bool))[0]

    if celdas.size == 0 or t < FECHAS_MINIMAS:
        return Cambios(
            orden=orden,
            confianza=confianza,
            delta_hv_db=delta,
            significativo=zeros(n, dtype=bool),
        )

    patrones: Arreglo = packbits(disponibles[:, celdas].T, axis=1)

    _, grupo = unique(patrones, axis=0, return_inverse=True)

    grupo = asarray(grupo).reshape(-1)

    for g in range(int(grupo.max()) + 1):
        miembros: Arreglo = celdas[grupo == g]

        fechas: Arreglo = where(disponibles[:, miembros[0]])[0]

        k: int = fechas.size

        if k < FECHAS_MINIMAS:
            continue

        perms: Arreglo = permutaciones(k, perfil.cusum_b, semilla)

        for inicio in range(0, miembros.size, BLOQUE_CELDAS):
            bloque: Arreglo = miembros[inicio : inicio + BLOQUE_CELDAS]

            series: Arreglo = datos[fechas][:, bloque].T

            corte, conf, dif = cusum_bloque(series, perms)

            orden[bloque] = fechas[corte]
            confianza[bloque] = conf
            delta[bloque] = dif

    significativo: Arreglo = (
        (orden != SIN_CAMBIO)
        & (confianza >= perfil.cusum_confianza)
        & (delta <= -perfil.cusum_perdida_db)
    )

    return Cambios(
        orden=orden,
        confianza=confianza,
        delta_hv_db=delta,
        significativo=significativo,
    )

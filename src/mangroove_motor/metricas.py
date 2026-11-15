from dataclasses import dataclass
from typing import TYPE_CHECKING

from numpy import (
    asarray,
    float64,
    full,
    int16,
    isfinite,
    nan,
    ones,
)
from scipy.ndimage import convolve

from mangroove_motor.perfil import Clase, Perfil

if TYPE_CHECKING:
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo

########################################################################################

VENTANA_MAYORIA: int = 3

########################################################################################


@dataclass(frozen=True, slots=True)
class Frecuencias:
    if_total: Arreglo
    if_alta: Arreglo
    n_fechas: Arreglo
    n_fechas_alta: Arreglo
    datos_suficientes: Arreglo


########################################################################################


def fraccion(conteo: Arreglo, total: Arreglo) -> Arreglo:
    salida: Arreglo = full(total.shape, nan, dtype=float64)

    hay: Arreglo = total > 0

    salida[hay] = conteo[hay] / total[hay]

    return salida


def frecuencias(clases: Arreglo, usadas_alta: Arreglo, perfil: Perfil) -> Frecuencias:
    con_dato: Arreglo = clases != Clase.ND
    inundada: Arreglo = (clases == Clase.IV) | (clases == Clase.OW)

    altas: Arreglo = asarray(usadas_alta, dtype=bool)[:, None] & con_dato

    n_fechas: Arreglo = con_dato.sum(axis=0)
    n_fechas_alta: Arreglo = altas.sum(axis=0)

    suficientes: Arreglo = n_fechas_alta >= perfil.min_fechas_alta

    if_alta: Arreglo = fraccion((inundada & altas).sum(axis=0), n_fechas_alta)

    if_alta[~suficientes] = nan

    return Frecuencias(
        if_total=fraccion((inundada & con_dato).sum(axis=0), n_fechas),
        if_alta=if_alta,
        n_fechas=n_fechas.astype(int16),
        n_fechas_alta=n_fechas_alta.astype(int16),
        datos_suficientes=suficientes,
    )


def inundacion_esperada(
    elevacion: Arreglo,
    mareas_altas: Arreglo,
    perfil: Perfil,
) -> Arreglo:
    cotas: Arreglo = asarray(elevacion, dtype=float64)
    mareas: Arreglo = asarray(mareas_altas, dtype=float64)

    salida: Arreglo = full(cotas.shape, nan, dtype=float64)

    if mareas.size == 0:
        return salida

    conocidas: Arreglo = isfinite(cotas)

    supera: Arreglo = mareas[:, None] > cotas[None, :] + perfil.marea_margen_m

    salida[conocidas] = supera.mean(axis=0)[conocidas]

    return salida


def voto_mayoria(marcadas: Arreglo, elegibles: Arreglo, grilla: Grilla) -> Arreglo:
    forma: tuple[int, int] = (grilla.alto, grilla.ancho)

    nucleo: Arreglo = ones((VENTANA_MAYORIA, VENTANA_MAYORIA), dtype=float64)

    a_favor: Arreglo = convolve(
        (marcadas & elegibles).reshape(forma).astype(float64),
        nucleo,
        mode="constant",
        cval=0.0,
    )

    vecinas: Arreglo = convolve(
        elegibles.reshape(forma).astype(float64),
        nucleo,
        mode="constant",
        cval=0.0,
    )

    return (elegibles.reshape(forma) & (2 * a_favor > vecinas)).reshape(grilla.n)


def desconexion(
    *,
    en_mascara: Arreglo,
    frecuencias_celda: Frecuencias,
    if_esperada: Arreglo | None,
    perfil: Perfil,
    grilla: Grilla,
) -> Arreglo:
    elegibles: Arreglo = (
        asarray(en_mascara, dtype=bool) & frecuencias_celda.datos_suficientes
    )

    marcadas: Arreglo = elegibles & (
        asarray(frecuencias_celda.if_alta) < perfil.if_alta_desconectada
    )

    if perfil.usar_elevacion and if_esperada is not None:
        esperada: Arreglo = asarray(if_esperada, dtype=float64)

        marcadas &= ~isfinite(esperada) | (esperada >= perfil.if_esperada_min)

    if not perfil.mayoria:
        return marcadas

    return voto_mayoria(marcadas, elegibles, grilla)

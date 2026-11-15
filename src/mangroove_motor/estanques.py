from dataclasses import dataclass, replace
from math import isnan
from typing import TYPE_CHECKING

from numpy import (
    asarray,
    float64,
    isfinite,
    nanmean,
    ones,
    unique,
    where,
)
from scipy.ndimage import binary_dilation, distance_transform_edt

from mangroove_motor.agregacion import a_lineal
from mangroove_motor.perfil import Banda, Clase, Perfil

if TYPE_CHECKING:
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo

########################################################################################

ANILLO_VECINO: int = 3

FECHAS_MINIMAS_CV: int = 2

########################################################################################


@dataclass(frozen=True, slots=True)
class ResultadoEstanque:
    numero: int
    n_celdas: int
    area_ha: float
    cv_hh: float
    cv_hv: float
    cv: float
    activo: bool
    dist_canal_km: float
    if_vecino: float | None
    puntaje: float | None


########################################################################################


def coeficiente_variacion(serie: Arreglo) -> float:
    valores: Arreglo = serie[isfinite(serie)]

    if valores.size < FECHAS_MINIMAS_CV:
        return float("nan")

    media: float = float(valores.mean())

    if media <= 0:
        return float("nan")

    return float(valores.std()) / media


def cv_por_tracks(serie: Arreglo, indice_track: Arreglo) -> float:
    total: float = 0.0
    peso: int = 0

    for j in unique(indice_track):
        fechas: Arreglo = serie[indice_track == j]

        cv: float = coeficiente_variacion(fechas)

        if not isnan(cv):
            n: int = int(isfinite(fechas).sum())

            total += cv * n
            peso += n

    return total / peso if peso else float("nan")


def serie_lineal(valores_db: Arreglo, celdas: Arreglo) -> Arreglo:
    lineales: Arreglo = a_lineal(valores_db[:, celdas])

    return nanmean(where(isfinite(lineales), lineales, float("nan")), axis=1)


def distancia_canal_km(tipica: Arreglo, estanques: Arreglo, grilla: Grilla) -> Arreglo:
    canal: Arreglo = (asarray(tipica) == Clase.OW) & (asarray(estanques) == 0)

    forma: tuple[int, int] = (grilla.alto, grilla.ancho)

    if not canal.any():
        return ones(grilla.n, dtype=float64) * float("inf")

    distancias: Arreglo = distance_transform_edt(~canal.reshape(forma))

    return asarray(distancias, dtype=float64).reshape(grilla.n) * grilla.celda_m / 1000


def inundacion_vecina(
    celdas_estanque: Arreglo,
    if_total: Arreglo,
    manglar: Arreglo,
    grilla: Grilla,
) -> float | None:
    forma: tuple[int, int] = (grilla.alto, grilla.ancho)

    lado: int = 2 * ANILLO_VECINO + 1

    region: Arreglo = binary_dilation(
        celdas_estanque.reshape(forma),
        structure=ones((lado, lado), dtype=bool),
    ).reshape(grilla.n)

    vecinas: Arreglo = region & asarray(manglar, dtype=bool) & isfinite(if_total)

    if not vecinas.any():
        return None

    return float(if_total[vecinas].mean())


def evaluar_estanques(  # ruff: ignore[too-many-arguments]
    *,
    estanques: Arreglo,
    hh: Arreglo,
    hv: Arreglo,
    indice_track: Arreglo,
    tipica: Arreglo,
    if_total: Arreglo,
    manglar: Arreglo,
    grilla: Grilla,
    perfil: Perfil,
) -> list[ResultadoEstanque]:
    numeros: Arreglo = asarray(estanques)

    distancias: Arreglo = distancia_canal_km(tipica, numeros, grilla)

    resultados: list[ResultadoEstanque] = []

    for numero in unique(numeros[numeros > 0]):
        celdas: Arreglo = numeros == numero

        cv_hh: float = cv_por_tracks(serie_lineal(hh, celdas), indice_track)
        cv_hv: float = cv_por_tracks(serie_lineal(hv, celdas), indice_track)

        cv: float = cv_hh if perfil.cv_banda == Banda.HH else cv_hv

        resultados.append(
            ResultadoEstanque(
                numero=int(numero),
                n_celdas=int(celdas.sum()),
                area_ha=float(celdas.sum()) * grilla.hectareas_por_celda,
                cv_hh=cv_hh,
                cv_hv=cv_hv,
                cv=cv,
                activo=bool(cv >= perfil.cv_estanque),
                dist_canal_km=float(distancias[celdas].min()),
                if_vecino=inundacion_vecina(celdas, if_total, manglar, grilla),
                puntaje=None,
            ),
        )

    return puntuar(resultados, perfil)


def puntuar(
    resultados: list[ResultadoEstanque], perfil: Perfil
) -> list[ResultadoEstanque]:
    abandonados: list[ResultadoEstanque] = [r for r in resultados if not r.activo]

    if not abandonados:
        return resultados

    finitas: list[float] = [
        r.dist_canal_km for r in abandonados if r.dist_canal_km != float("inf")
    ]

    area_max: float = max(1e-9, *(r.area_ha for r in abandonados))
    dist_max: float = max(1e-9, *finitas) if finitas else 1e-9

    def puntaje(r: ResultadoEstanque) -> float:
        cercania: float = (
            0.0 if r.dist_canal_km == float("inf") else 1 - r.dist_canal_km / dist_max
        )

        return (
            perfil.puntaje_distancia * cercania
            + perfil.puntaje_area * r.area_ha / area_max
            + perfil.puntaje_inundacion * (r.if_vecino or 0.0)
        )

    return [replace(r, puntaje=None if r.activo else puntaje(r)) for r in resultados]

from dataclasses import dataclass
from typing import TYPE_CHECKING

from numpy import (
    asarray,
    float32,
    float64,
    full,
    isfinite,
    median,
    nan,
    unique,
    where,
    zeros,
)

from mangroove_motor.agregacion import a_db, a_lineal

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mangroove_motor.perfil import Perfil
    from mangroove_motor.types import Arreglo

########################################################################################


@dataclass(frozen=True, slots=True)
class Calibrado:
    hh: Arreglo
    hv: Arreglo
    desfase_hh: Arreglo
    desfase_hv: Arreglo
    tracks: Arreglo
    indice_track: Arreglo
    media_hh: Arreglo
    media_hv: Arreglo
    n_estables: int

    def media_hh_por_fecha(self) -> Arreglo:
        return self.media_hh[self.indice_track]

    def media_hv_por_fecha(self) -> Arreglo:
        return self.media_hv[self.indice_track]

    def fechas_de(self, k: int) -> Arreglo:
        return where(self.indice_track == k)[0]


########################################################################################


def media_lineal(valores: Arreglo) -> Arreglo:
    datos: Arreglo = asarray(valores, dtype=float64)

    finitos: Arreglo = isfinite(datos)

    conteo: Arreglo = finitos.sum(axis=0)

    suma: Arreglo = where(finitos, a_lineal(where(finitos, datos, 0.0)), 0.0).sum(
        axis=0
    )

    salida: Arreglo = full(datos.shape[1:], nan, dtype=float64)

    hay: Arreglo = conteo > 0

    salida[hay] = a_db(suma[hay] / conteo[hay])

    return salida


def medias_por_track(
    hh: Arreglo,
    hv: Arreglo,
    indice_track: Arreglo,
    k: int,
) -> tuple[Arreglo, Arreglo]:
    n: int = hh.shape[1]

    media_hh: Arreglo = full((k, n), nan, dtype=float64)
    media_hv: Arreglo = full((k, n), nan, dtype=float64)

    for j in range(k):
        fechas: Arreglo = where(indice_track == j)[0]

        media_hh[j] = media_lineal(hh[fechas])
        media_hv[j] = media_lineal(hv[fechas])

    return media_hh, media_hv


def elegir_estables(
    candidatas: Sequence[Arreglo],
    utilizables: Arreglo,
    minimas: int,
) -> Arreglo:
    for candidata in candidatas:
        elegidas: Arreglo = asarray(candidata, dtype=bool) & utilizables

        if int(elegidas.sum()) >= minimas:
            return elegidas

    return utilizables


def desfase(valores: Arreglo, referencia: Arreglo, estables: Arreglo) -> float:
    diferencias: Arreglo = valores[estables] - referencia[estables]

    diferencias = diferencias[isfinite(diferencias)]

    if diferencias.size == 0:
        return 0.0

    return float(median(diferencias))


def calibrar(
    hh: Arreglo,
    hv: Arreglo,
    tracks: Arreglo,
    *,
    candidatas: Sequence[Arreglo],
    perfil: Perfil,
) -> Calibrado:
    datos_hh: Arreglo = asarray(hh, dtype=float64)
    datos_hv: Arreglo = asarray(hv, dtype=float64)

    unicos, indice_track = unique(asarray(tracks), return_inverse=True)

    media_hh, media_hv = medias_por_track(datos_hh, datos_hv, indice_track, len(unicos))

    agua: Arreglo = ((media_hh < perfil.ow_hh_db) & (media_hv < perfil.ow_hv_db)).any(
        axis=0,
    )

    utilizables: Arreglo = (
        isfinite(media_hh).all(axis=0) & isfinite(media_hv).all(axis=0) & ~agua
    )

    estables: Arreglo = elegir_estables(
        candidatas, utilizables, perfil.estables_minimas
    )

    t: int = datos_hh.shape[0]

    desfase_hh: Arreglo = zeros(t, dtype=float64)
    desfase_hv: Arreglo = zeros(t, dtype=float64)

    for i in range(t):
        j: int = int(indice_track[i])

        desfase_hh[i] = desfase(datos_hh[i], media_hh[j], estables)
        desfase_hv[i] = desfase(datos_hv[i], media_hv[j], estables)

    calibrado_hh: Arreglo = datos_hh - desfase_hh[:, None]
    calibrado_hv: Arreglo = datos_hv - desfase_hv[:, None]

    media_hh, media_hv = medias_por_track(
        calibrado_hh,
        calibrado_hv,
        indice_track,
        len(unicos),
    )

    return Calibrado(
        hh=calibrado_hh.astype(float32),
        hv=calibrado_hv.astype(float32),
        desfase_hh=desfase_hh,
        desfase_hv=desfase_hv,
        tracks=unicos,
        indice_track=indice_track,
        media_hh=media_hh,
        media_hv=media_hv,
        n_estables=int(estables.sum()),
    )

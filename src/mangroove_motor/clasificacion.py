from dataclasses import dataclass
from typing import TYPE_CHECKING

from numpy import (
    abs as np_abs,
    argmax,
    asarray,
    errstate,
    float64,
    full,
    isfinite,
    maximum,
    minimum,
    nan,
    select,
    stack,
    uint8,
    where,
    zeros,
)
from scipy.special import ndtr

from mangroove_motor.perfil import Clase, Perfil

if TYPE_CHECKING:
    from mangroove_motor.calibracion import Calibrado
    from mangroove_motor.types import Arreglo

########################################################################################

CLASES_TIPICAS: tuple[Clase, ...] = (Clase.NI, Clase.IV, Clase.OW)

ESCALA_COHERENCIA: float = 10.0

########################################################################################


@dataclass(frozen=True, slots=True)
class Clasificacion:
    clases: Arreglo
    margenes: Arreglo
    tipica: Arreglo
    tipica_track: Arreglo
    p_error: Arreglo


########################################################################################


def clase_estatica(hh: Arreglo, hv: Arreglo, perfil: Perfil) -> Arreglo:
    h: Arreglo = asarray(hh, dtype=float64)
    v: Arreglo = asarray(hv, dtype=float64)

    with errstate(invalid="ignore"):
        return select(
            [
                ~isfinite(h) | ~isfinite(v),
                (h < perfil.ow_hh_db) & (v < perfil.ow_hv_db),
                (h > perfil.iv_hh_db) & (h - v > perfil.iv_ratio_db),
            ],
            [Clase.ND, Clase.OW, Clase.IV],
            default=Clase.NI,
        ).astype(uint8)


def clases_tipicas(calibrado: Calibrado, perfil: Perfil) -> tuple[Arreglo, Arreglo]:
    tipica_track: Arreglo = clase_estatica(
        calibrado.media_hh, calibrado.media_hv, perfil
    )

    k, n = tipica_track.shape

    validas: Arreglo = zeros((k, n), dtype=float64)

    for j in range(k):
        fechas: Arreglo = calibrado.fechas_de(j)

        validas[j] = (
            isfinite(calibrado.hh[fechas]) & isfinite(calibrado.hv[fechas])
        ).sum(axis=0)

    votos: Arreglo = stack([
        ((tipica_track == clase) * validas).sum(axis=0) for clase in CLASES_TIPICAS
    ])

    ganadora: Arreglo = asarray(CLASES_TIPICAS, dtype=uint8)[argmax(votos, axis=0)]

    return tipica_track, where(votos.sum(axis=0) > 0, ganadora, Clase.ND).astype(uint8)


def clasificar(
    calibrado: Calibrado,
    perfil: Perfil,
    coherencia: Arreglo | None = None,
) -> Clasificacion:
    h: Arreglo = asarray(calibrado.hh, dtype=float64)
    v: Arreglo = asarray(calibrado.hv, dtype=float64)

    tipica_track, tipica = clases_tipicas(calibrado, perfil)

    tipo: Arreglo = tipica_track[calibrado.indice_track]

    with errstate(invalid="ignore"):
        r: Arreglo = h - v
        dh: Arreglo = h - calibrado.media_hh_por_fecha()
        dv: Arreglo = v - calibrado.media_hv_por_fecha()

        estable_hv: Arreglo = np_abs(dv) < perfil.cambio_hv_db

        condiciones: list[Arreglo] = [
            ~isfinite(h) | ~isfinite(v),
            (h < perfil.ow_hh_db) & (v < perfil.ow_hv_db),
            (h > perfil.iv_hh_db) & (r > perfil.iv_ratio_db),
            (tipo == Clase.IV) & (dh < -perfil.cambio_hh_db) & estable_hv,
            (tipo != Clase.IV)
            & (tipo != Clase.OW)
            & (dh > perfil.cambio_hh_db)
            & estable_hv
            & (r > perfil.iv_ratio_db - perfil.iv_ratio_holgura_db),
            (h > perfil.nc_hh_db) | (v > perfil.nc_hv_db),
        ]

        clases: Arreglo = select(
            condiciones,
            [Clase.ND, Clase.OW, Clase.IV, Clase.NI, Clase.IV, Clase.NC],
            default=Clase.NI,
        ).astype(uint8)

        margenes: Arreglo = select(
            condiciones,
            [
                full(h.shape, nan),
                minimum(perfil.ow_hh_db - h, perfil.ow_hv_db - v),
                minimum(h - perfil.iv_hh_db, r - perfil.iv_ratio_db),
                -dh - perfil.cambio_hh_db,
                dh - perfil.cambio_hh_db,
                maximum(h - perfil.nc_hh_db, v - perfil.nc_hv_db),
            ],
            default=minimum(
                minimum(np_abs(h - perfil.ow_hh_db), np_abs(h - perfil.iv_hh_db)),
                np_abs(r - perfil.iv_ratio_db) + maximum(0.0, perfil.iv_hh_db - h),
            ),
        )

        if coherencia is not None and perfil.usar_coherencia:
            coh: Arreglo = asarray(coherencia, dtype=float64)

            lodo: Arreglo = (clases == Clase.OW) & (coh > perfil.coherencia_min)

            clases[lodo] = Clase.NI
            margenes = where(
                lodo,
                np_abs(coh - perfil.coherencia_min) * ESCALA_COHERENCIA,
                margenes,
            )

    return Clasificacion(
        clases=clases,
        margenes=margenes,
        tipica=tipica,
        tipica_track=tipica_track,
        p_error=probabilidad_error(clases, margenes, perfil.sigma_db),
    )


def probabilidad_error(clases: Arreglo, margenes: Arreglo, sigma: float) -> Arreglo:
    con_dato: Arreglo = clases != Clase.ND

    errores: Arreglo = where(con_dato, ndtr(-np_abs(margenes) / sigma), 0.0)

    fechas: Arreglo = con_dato.sum(axis=0)

    salida: Arreglo = full(clases.shape[1], nan, dtype=float64)

    hay: Arreglo = fechas > 0

    salida[hay] = errores.sum(axis=0)[hay] / fechas[hay]

    return salida

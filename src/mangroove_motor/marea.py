from datetime import UTC, datetime
from itertools import pairwise
from typing import TYPE_CHECKING

from numpy import asarray, float64, full, isfinite
from numpy.ma import filled, getmaskarray
from pyTMD.compute import tide_elevations

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from mangroove_motor.types import Arreglo

########################################################################################

EPOCA: datetime = datetime(2000, 1, 1, tzinfo=UTC)

########################################################################################


def segundos_desde_epoca(instantes: Sequence[datetime]) -> Arreglo:
    return asarray([(t - EPOCA).total_seconds() for t in instantes], dtype=float64)


def alturas_marea(
    instantes: Sequence[datetime],
    *,
    lon: float,
    lat: float,
    directorio: Path,
    modelo: str,
) -> list[float | None]:
    if not instantes:
        return []

    n: int = len(instantes)

    crudas = tide_elevations(
        full(n, lon, dtype=float64),
        full(n, lat, dtype=float64),
        segundos_desde_epoca(instantes),
        crs=4326,
        directory=directorio,
        epoch=(2000, 1, 1, 0, 0, 0),
        model=modelo,
        standard="UTC",
        type="trajectory",
    )

    mascara: Arreglo = getmaskarray(crudas)
    valores: Arreglo = asarray(filled(crudas, float("nan")), dtype=float64).reshape(n)

    return [
        None
        if bool(mascara.reshape(-1)[i]) or not isfinite(valores[i])
        else round(float(valores[i]), 4)
        for i in range(n)
    ]


def interpolar_serie(
    instantes: Sequence[datetime],
    serie: Sequence[tuple[datetime, float]],
) -> list[float | None]:
    ordenada: list[tuple[datetime, float]] = sorted(serie)

    salida: list[float | None] = []

    for instante in instantes:
        valor: float | None = None

        for (t0, v0), (t1, v1) in pairwise(ordenada):
            if t0 <= instante <= t1:
                fraccion: float = (
                    0.0
                    if t1 == t0
                    else (instante - t0).total_seconds() / (t1 - t0).total_seconds()
                )

                valor = round(v0 + (v1 - v0) * fraccion, 4)

                break

        salida.append(valor)

    return salida

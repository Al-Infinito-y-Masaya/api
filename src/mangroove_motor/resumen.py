from dataclasses import dataclass
from typing import TYPE_CHECKING

from numpy import asarray, ones, uint8

from mangroove_motor.perfil import Clase

if TYPE_CHECKING:
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo

########################################################################################

REGION_COMPLETA: str = ""

########################################################################################


@dataclass(frozen=True, slots=True)
class ResumenPais:
    pais: str
    n_celdas: int
    ha_manglar: float
    ha_desconectada: float
    ha_insuficiente: float
    ha_perdida_copa: float
    ha_iv_tipica: float
    ha_ow_tipica: float
    ha_ni_tipica: float


@dataclass(frozen=True, slots=True)
class ResumenFecha:
    orden: int
    pais: str
    ha_iv: float
    ha_ow: float
    ha_ni: float
    ha_nc: float
    ha_nd: float


########################################################################################


def ambitos(
    paises: Arreglo | None, codigos: tuple[str, ...], n: int
) -> list[tuple[str, Arreglo]]:
    todos: list[tuple[str, Arreglo]] = [(REGION_COMPLETA, ones(n, dtype=bool))]

    if paises is None:
        return todos

    indices: Arreglo = asarray(paises, dtype=uint8)

    return todos + [
        (codigo, indices == posicion)
        for posicion, codigo in enumerate(codigos, 1)
        if (indices == posicion).any()
    ]


def resumir(  # ruff: ignore[too-many-arguments]
    *,
    grilla: Grilla,
    manglar: Arreglo,
    desconectada: Arreglo,
    suficientes: Arreglo,
    perdida: Arreglo,
    tipica: Arreglo,
    clases: Arreglo,
    paises: Arreglo | None,
    codigos_paises: tuple[str, ...],
) -> tuple[list[ResumenPais], list[ResumenFecha]]:
    ha: float = grilla.hectareas_por_celda

    mascara: Arreglo = asarray(manglar, dtype=bool)

    por_pais: list[ResumenPais] = []
    por_fecha: list[ResumenFecha] = []

    for pais, ambito in ambitos(paises, codigos_paises, grilla.n):
        en: Arreglo = ambito & mascara

        por_pais.append(
            ResumenPais(
                pais=pais,
                n_celdas=int(ambito.sum()),
                ha_manglar=float(en.sum()) * ha,
                ha_desconectada=float((en & desconectada).sum()) * ha,
                ha_insuficiente=float((en & ~suficientes).sum()) * ha,
                ha_perdida_copa=float((en & perdida).sum()) * ha,
                ha_iv_tipica=float((en & (tipica == Clase.IV)).sum()) * ha,
                ha_ow_tipica=float((en & (tipica == Clase.OW)).sum()) * ha,
                ha_ni_tipica=float((en & (tipica == Clase.NI)).sum()) * ha,
            ),
        )

        for orden in range(clases.shape[0]):
            fila: Arreglo = clases[orden][en]

            por_fecha.append(
                ResumenFecha(
                    orden=orden,
                    pais=pais,
                    ha_iv=float((fila == Clase.IV).sum()) * ha,
                    ha_ow=float((fila == Clase.OW).sum()) * ha,
                    ha_ni=float((fila == Clase.NI).sum()) * ha,
                    ha_nc=float((fila == Clase.NC).sum()) * ha,
                    ha_nd=float((fila == Clase.ND).sum()) * ha,
                ),
            )

    return por_pais, por_fecha

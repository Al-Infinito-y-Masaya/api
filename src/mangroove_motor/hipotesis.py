from dataclasses import dataclass
from enum import StrEnum
from math import sqrt
from typing import TYPE_CHECKING

from numpy import (
    asarray,
    concatenate,
    float64,
    isfinite,
    median,
    ones,
    quantile,
    unique,
)
from scipy.ndimage import distance_transform_edt
from scipy.special import ndtr
from scipy.stats import fisher_exact, rankdata

from mangroove_motor.perfil import Clase

if TYPE_CHECKING:
    from mangroove_motor.estanques import ResultadoEstanque
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo

########################################################################################

MUESTRA_MINIMA: int = 5

CERCA: float = 1.5

LEJOS_DE_BARRERA: float = 3.0

PERCENTIL_BAJO: float = 0.1
PERCENTIL_ALTO: float = 0.9

########################################################################################


class Prueba(StrEnum):
    MANN_WHITNEY = "mann_whitney"
    FISHER = "fisher"


@dataclass(frozen=True, slots=True)
class ResultadoPrueba:
    codigo: str
    prueba: Prueba
    grupo_a: str
    grupo_b: str
    n_a: int
    n_b: int
    evaluable: bool
    motivo: str = ""
    mediana_a: float | None = None
    mediana_b: float | None = None
    estadistico: float | None = None
    z: float | None = None
    p_valor: float | None = None
    efecto: float | None = None


########################################################################################


def mann_whitney(a: Arreglo, b: Arreglo) -> tuple[float, float, float, float]:
    n1, n2 = a.size, b.size

    todos: Arreglo = concatenate([a, b])

    rangos: Arreglo = rankdata(todos)

    _, repeticiones = unique(todos, return_counts=True)

    empates: float = float((repeticiones**3 - repeticiones).sum())

    u: float = float(rangos[:n1].sum()) - n1 * (n1 + 1) / 2

    n: int = n1 + n2

    sd: float = sqrt(n1 * n2 / 12 * ((n + 1) - empates / (n * (n - 1))))

    z: float = (u - n1 * n2 / 2) / sd if sd > 0 else 0.0

    return u, z, float(2 * ndtr(-abs(z))), z / sqrt(n)


def comparar_medianas(
    codigo: str,
    grupos: tuple[str, str],
    a: Arreglo,
    b: Arreglo,
) -> ResultadoPrueba:
    valores_a: Arreglo = asarray(a, dtype=float64)
    valores_b: Arreglo = asarray(b, dtype=float64)

    valores_a = valores_a[isfinite(valores_a)]
    valores_b = valores_b[isfinite(valores_b)]

    base: dict = {
        "codigo": codigo,
        "grupo_a": grupos[0],
        "grupo_b": grupos[1],
        "n_a": int(valores_a.size),
        "n_b": int(valores_b.size),
        "prueba": Prueba.MANN_WHITNEY,
    }

    if min(valores_a.size, valores_b.size) < MUESTRA_MINIMA:
        return ResultadoPrueba(
            **base,
            evaluable=False,
            motivo=f"Menos de {MUESTRA_MINIMA} elementos en algún grupo.",
        )

    u, z, p, r = mann_whitney(valores_a, valores_b)

    return ResultadoPrueba(
        **base,
        evaluable=True,
        mediana_a=float(median(valores_a)),
        mediana_b=float(median(valores_b)),
        estadistico=u,
        z=z,
        p_valor=p,
        efecto=r,
    )


def comparar_proporciones(
    codigo: str,
    grupos: tuple[str, str],
    a: Arreglo,
    b: Arreglo,
) -> ResultadoPrueba:
    marcas_a: Arreglo = asarray(a, dtype=bool)
    marcas_b: Arreglo = asarray(b, dtype=bool)

    base: dict = {
        "codigo": codigo,
        "grupo_a": grupos[0],
        "grupo_b": grupos[1],
        "n_a": int(marcas_a.size),
        "n_b": int(marcas_b.size),
        "prueba": Prueba.FISHER,
    }

    if min(marcas_a.size, marcas_b.size) < MUESTRA_MINIMA:
        return ResultadoPrueba(
            **base,
            evaluable=False,
            motivo=f"Menos de {MUESTRA_MINIMA} elementos en algún grupo.",
        )

    tabla: list[list[int]] = [
        [int(marcas_a.sum()), int((~marcas_a).sum())],
        [int(marcas_b.sum()), int((~marcas_b).sum())],
    ]

    razon, p = fisher_exact(tabla)

    return ResultadoPrueba(
        **base,
        evaluable=True,
        mediana_a=float(marcas_a.mean()),
        mediana_b=float(marcas_b.mean()),
        estadistico=float(razon),
        p_valor=float(p),
        efecto=float(marcas_a.mean() - marcas_b.mean()),
    )


########################################################################################


def distancia_celdas(marcadas: Arreglo, grilla: Grilla) -> Arreglo:
    forma: tuple[int, int] = (grilla.alto, grilla.ancho)

    marca: Arreglo = asarray(marcadas, dtype=bool)

    if not marca.any():
        return ones(grilla.n, dtype=float64) * float("inf")

    return asarray(
        distance_transform_edt(~marca.reshape(forma)),
        dtype=float64,
    ).reshape(grilla.n)


def estratos(  # ruff: ignore[too-many-arguments]
    *,
    manglar: Arreglo,
    suficientes: Arreglo,
    barreras: Arreglo,
    tipica: Arreglo,
    estanques: Arreglo | None,
    elevacion: Arreglo | None,
    grilla: Grilla,
) -> tuple[Arreglo, Arreglo] | None:
    if not asarray(barreras).any():
        return None

    canal: Arreglo = asarray(tipica) == Clase.OW

    if estanques is not None:
        canal &= asarray(estanques) == 0

    d_barrera: Arreglo = distancia_celdas(asarray(barreras) > 0, grilla)
    d_canal: Arreglo = distancia_celdas(canal, grilla)

    base: Arreglo = asarray(manglar, dtype=bool) & asarray(suficientes, dtype=bool)

    junto_barrera: Arreglo = base & (d_barrera <= CERCA)
    junto_canal: Arreglo = base & (d_canal <= CERCA) & (d_barrera > LEJOS_DE_BARRERA)

    if elevacion is not None and junto_barrera.any() and junto_canal.any():
        cotas: Arreglo = asarray(elevacion, dtype=float64)

        bajo: float = max(
            float(quantile(cotas[junto_barrera], PERCENTIL_BAJO)),
            float(quantile(cotas[junto_canal], PERCENTIL_BAJO)),
        )
        alto: float = min(
            float(quantile(cotas[junto_barrera], PERCENTIL_ALTO)),
            float(quantile(cotas[junto_canal], PERCENTIL_ALTO)),
        )

        rango: Arreglo = (cotas >= bajo) & (cotas <= alto)

        junto_barrera &= rango
        junto_canal &= rango

    return junto_barrera, junto_canal


def probar_hipotesis(  # ruff: ignore[too-many-arguments]
    *,
    if_alta: Arreglo,
    perdida: Arreglo,
    desconectada: Arreglo,
    grupos: tuple[Arreglo, Arreglo] | None,
    resultados_estanques: list[ResultadoEstanque],
    estanques: Arreglo | None,
    grilla: Grilla,
) -> list[ResultadoPrueba]:
    sin_barreras: str = "No hay bordas ni caminos digitalizados en la región."

    nombres: tuple[str, str] = ("junto a bordas", "junto a canales")

    if grupos is None:
        h1: ResultadoPrueba = ResultadoPrueba(
            codigo="H1",
            prueba=Prueba.MANN_WHITNEY,
            grupo_a=nombres[0],
            grupo_b=nombres[1],
            n_a=0,
            n_b=0,
            evaluable=False,
            motivo=sin_barreras,
        )
        h2: ResultadoPrueba = ResultadoPrueba(
            codigo="H2",
            prueba=Prueba.FISHER,
            grupo_a=nombres[0],
            grupo_b=nombres[1],
            n_a=0,
            n_b=0,
            evaluable=False,
            motivo=sin_barreras,
        )
    else:
        a, b = grupos

        h1 = comparar_medianas("H1", nombres, asarray(if_alta)[a], asarray(if_alta)[b])
        h2 = comparar_proporciones(
            "H2", nombres, asarray(perdida)[a], asarray(perdida)[b]
        )

    return [
        h1,
        h2,
        hipotesis_estanques(resultados_estanques, estanques, desconectada, grilla),
    ]


def hipotesis_estanques(
    resultados: list[ResultadoEstanque],
    estanques: Arreglo | None,
    desconectada: Arreglo,
    grilla: Grilla,
) -> ResultadoPrueba:
    nombres: tuple[str, str] = ("estanques abandonados", "estanques activos")

    if estanques is None or not resultados:
        return ResultadoPrueba(
            codigo="H3",
            prueba=Prueba.MANN_WHITNEY,
            grupo_a=nombres[0],
            grupo_b=nombres[1],
            n_a=0,
            n_b=0,
            evaluable=False,
            motivo="No hay estanques digitalizados en la región.",
        )

    distancias: Arreglo = distancia_celdas(desconectada, grilla) * grilla.celda_m / 1000

    numeros: Arreglo = asarray(estanques)

    def minima(r: ResultadoEstanque) -> float:
        return float(distancias[numeros == r.numero].min())

    return comparar_medianas(
        "H3",
        nombres,
        asarray([minima(r) for r in resultados if not r.activo]),
        asarray([minima(r) for r in resultados if r.activo]),
    )

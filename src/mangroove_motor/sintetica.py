from dataclasses import dataclass
from math import pi, sin
from typing import TYPE_CHECKING

from numpy import (
    arange,
    float32,
    full,
    int32,
    meshgrid,
    uint8,
    zeros,
)
from numpy.random import default_rng

from mangroove_motor.datos import Auxiliares, Fecha, Pila
from mangroove_motor.grilla import Grilla
from mangroove_motor.perfil import Clase

if TYPE_CHECKING:
    from mangroove_motor.types import Arreglo

########################################################################################

ANCHO: int = 80
ALTO: int = 60
FECHAS: int = 30

TRACKS: tuple[int, ...] = (33, 98, 26)
BRILLO_TRACK: dict[int, float] = {33: 0.0, 98: -0.8, 26: 0.6}

CANAL: range = range(5)
CONECTADO: range = range(5, 35)
BORDA: range = range(35, 37)
DESCONECTADO: range = range(37, 57)
BORDA_ESTANQUES: range = range(57, 58)
ESTANQUES: range = range(58, 70)
TIERRA: range = range(70, 80)

FILA_PERDIDA: int = 30
FECHA_PERDIDA: int = FECHAS // 2

CICLO_ESTANQUE: int = 4
FECHAS_LLENO: int = 2

RUIDO_DB: float = 0.5
JITTER_DB: float = 0.3

AGUA: tuple[float, float] = (-21.5, -28.0)
BORDA_DB: tuple[float, float] = (-10.0, -17.5)
TIERRA_DB: tuple[float, float] = (-11.0, -17.5)
ESTANQUE_SECO: tuple[float, float] = (-13.0, -21.0)
ESTANQUE_ABANDONADO: tuple[float, float] = (-11.2, -17.8)

HV_MANGLAR: float = -11.4
HH_INUNDADO: float = -4.2
HH_SECO: float = -8.6
PERDIDA_HH: float = 2.4
PERDIDA_HV: float = 4.2

########################################################################################


@dataclass(frozen=True, slots=True)
class Verdad:
    clases: Arreglo
    desconectada: Arreglo
    perdida: Arreglo
    fecha_perdida: int
    estanques_activos: dict[int, bool]


@dataclass(frozen=True, slots=True)
class Escena:
    grilla: Grilla
    pila: Pila
    auxiliares: Auxiliares
    verdad: Verdad


########################################################################################


def marea(t: int) -> float:
    return round(1.3 * sin(2 * pi * t * 0.37) + 0.1, 3)


def mapa_estanques() -> tuple[Arreglo, dict[int, bool]]:
    numeros: Arreglo = zeros((ALTO, ANCHO), dtype=int32)

    mitad_x: int = ESTANQUES.start + len(ESTANQUES) // 2
    mitad_y: int = ALTO // 2

    numeros[:mitad_y, ESTANQUES.start : mitad_x] = 1
    numeros[:mitad_y, mitad_x : ESTANQUES.stop] = 2
    numeros[mitad_y:, ESTANQUES.start : mitad_x] = 3
    numeros[mitad_y:, mitad_x : ESTANQUES.stop] = 4

    return numeros, {1: True, 2: True, 3: False, 4: False}


def generar(semilla: int = 7) -> Escena:  # ruff: ignore[too-many-locals, too-many-statements]
    generador = default_rng(semilla)

    grilla: Grilla = Grilla(
        epsg=32616,
        x0=400_000.0,
        y0=1_450_000.0,
        celda_m=100.0,
        ancho=ANCHO,
        alto=ALTO,
    )

    xs, _ = meshgrid(arange(ANCHO), arange(ALTO))

    elevacion: Arreglo = full((ALTO, ANCHO), 3.0, dtype=float32)
    elevacion[:, CONECTADO.start : CONECTADO.stop] = 0.1 + 0.6 * (
        xs[:, CONECTADO.start : CONECTADO.stop] - CONECTADO.start
    ) / (len(CONECTADO) - 1)

    hv_base: Arreglo = HV_MANGLAR + 0.8 * generador.standard_normal((ALTO, ANCHO))

    estanques, activos = mapa_estanques()

    fechas: list[Fecha] = [
        Fecha(track=TRACKS[t % len(TRACKS)], marea_m=marea(t)) for t in range(FECHAS)
    ]

    hh: Arreglo = zeros((FECHAS, ALTO, ANCHO), dtype=float32)
    hv: Arreglo = zeros((FECHAS, ALTO, ANCHO), dtype=float32)
    clases: Arreglo = zeros((FECHAS, ALTO, ANCHO), dtype=uint8)

    perdida_zona: Arreglo = zeros((ALTO, ANCHO), dtype=bool)
    perdida_zona[:FILA_PERDIDA, DESCONECTADO.start : DESCONECTADO.stop] = True

    for t, fecha in enumerate(fechas):
        h: Arreglo = zeros((ALTO, ANCHO), dtype=float32)
        v: Arreglo = zeros((ALTO, ANCHO), dtype=float32)
        c: Arreglo = full((ALTO, ANCHO), Clase.NI, dtype=uint8)

        h[:, CANAL.start : CANAL.stop], v[:, CANAL.start : CANAL.stop] = AGUA
        c[:, CANAL.start : CANAL.stop] = Clase.OW

        zona: slice = slice(CONECTADO.start, CONECTADO.stop)

        inundada: Arreglo = (fecha.marea_m or 0.0) > elevacion[:, zona]

        h[:, zona] = HH_SECO
        h[:, zona][inundada] = HH_INUNDADO
        v[:, zona] = hv_base[:, zona] + 0.5 * inundada
        c[:, zona][inundada] = Clase.IV

        for borde in (BORDA, BORDA_ESTANQUES):
            h[:, borde.start : borde.stop], v[:, borde.start : borde.stop] = BORDA_DB

        zona = slice(DESCONECTADO.start, DESCONECTADO.stop)

        perdida: float = 1.0 if t >= FECHA_PERDIDA else 0.0

        perdio: Arreglo = perdida_zona[:, zona] * perdida

        h[:, zona] = HH_SECO - PERDIDA_HH * perdio
        v[:, zona] = hv_base[:, zona] - PERDIDA_HV * perdio

        for numero, activo in activos.items():
            celdas: Arreglo = estanques == numero

            if not activo:
                h[celdas], v[celdas] = ESTANQUE_ABANDONADO
            elif t % CICLO_ESTANQUE < FECHAS_LLENO:
                h[celdas], v[celdas] = AGUA
                c[celdas] = Clase.OW
            else:
                h[celdas], v[celdas] = ESTANQUE_SECO

        h[:, TIERRA.start : TIERRA.stop], v[:, TIERRA.start : TIERRA.stop] = TIERRA_DB

        sesgo: float = BRILLO_TRACK[fecha.track] + JITTER_DB * float(
            generador.standard_normal(),
        )

        hh[t] = h + sesgo + RUIDO_DB * generador.standard_normal((ALTO, ANCHO))
        hv[t] = v + sesgo + RUIDO_DB * generador.standard_normal((ALTO, ANCHO))
        clases[t] = c

    manglar: Arreglo = zeros((ALTO, ANCHO), dtype=bool)
    manglar[:, CONECTADO.start : CONECTADO.stop] = True
    manglar[:, DESCONECTADO.start : DESCONECTADO.stop] = True

    exclusion: Arreglo = zeros((ALTO, ANCHO), dtype=bool)
    exclusion[:, TIERRA.start : TIERRA.stop] = True

    barreras: Arreglo = zeros((ALTO, ANCHO), dtype=uint8)
    barreras[:, BORDA.start : BORDA.stop] = 1
    barreras[:, BORDA_ESTANQUES.start : BORDA_ESTANQUES.stop] = 1

    paises: Arreglo = zeros((ALTO, ANCHO), dtype=uint8)
    paises[:, : ANCHO // 2] = 1
    paises[:, ANCHO // 2 :] = 2

    desconectada: Arreglo = zeros((ALTO, ANCHO), dtype=bool)
    desconectada[:, DESCONECTADO.start : DESCONECTADO.stop] = True

    n: int = grilla.n

    return Escena(
        grilla=grilla,
        pila=Pila(
            hh=hh.reshape(FECHAS, n), hv=hv.reshape(FECHAS, n), fechas=tuple(fechas)
        ),
        auxiliares=Auxiliares(
            manglar=manglar.reshape(n),
            exclusion=exclusion.reshape(n),
            barreras=barreras.reshape(n),
            estanques=estanques.reshape(n),
            paises=paises.reshape(n),
            codigos_paises=("NI", "HN"),
        ),
        verdad=Verdad(
            clases=clases.reshape(FECHAS, n),
            desconectada=desconectada.reshape(n),
            perdida=perdida_zona.reshape(n),
            fecha_perdida=FECHA_PERDIDA,
            estanques_activos=activos,
        ),
    )

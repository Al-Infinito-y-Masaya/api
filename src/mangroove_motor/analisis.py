from dataclasses import dataclass
from typing import TYPE_CHECKING

from numpy import asarray, float64

from mangroove_motor.auxiliares import mascara_humedal
from mangroove_motor.calibracion import Calibrado, calibrar
from mangroove_motor.clasificacion import Clasificacion, clasificar
from mangroove_motor.cusum import Cambios, anomalias, detectar_cambios
from mangroove_motor.estanques import ResultadoEstanque, evaluar_estanques
from mangroove_motor.hipotesis import ResultadoPrueba, estratos, probar_hipotesis
from mangroove_motor.metricas import (
    Frecuencias,
    desconexion,
    frecuencias,
    inundacion_esperada,
)
from mangroove_motor.resumen import ResumenFecha, ResumenPais, resumir

if TYPE_CHECKING:
    from mangroove_motor.datos import Auxiliares, Pila
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.perfil import Perfil
    from mangroove_motor.types import Arreglo

########################################################################################


@dataclass(frozen=True, slots=True)
class Resultado:
    calibrado: Calibrado
    clasificacion: Clasificacion
    frecuencias: Frecuencias
    usadas_alta: Arreglo
    humedal: Arreglo
    en_mascara: Arreglo
    if_esperada: Arreglo | None
    desconectada: Arreglo
    cambios: Cambios
    estanques: list[ResultadoEstanque]
    hipotesis: list[ResultadoPrueba]
    resumen_pais: list[ResumenPais]
    resumen_fecha: list[ResumenFecha]


########################################################################################


def analizar(  # ruff: ignore[too-many-arguments]
    *,
    pila: Pila,
    auxiliares: Auxiliares,
    grilla: Grilla,
    perfil: Perfil,
    semilla: int,
    cambios_previos: Cambios | None = None,
) -> Resultado:
    manglar: Arreglo = asarray(auxiliares.manglar, dtype=bool)

    humedal: Arreglo = mascara_humedal(
        grilla,
        elevacion=auxiliares.elevacion,
        exclusion=auxiliares.exclusion,
        pendiente_max=perfil.humedal_pendiente_max,
        cota_max=perfil.humedal_cota_max,
    )

    calibrado: Calibrado = calibrar(
        pila.hh,
        pila.hv,
        pila.tracks,
        candidatas=(~humedal, ~manglar),
        perfil=perfil,
    )

    clasificacion: Clasificacion = clasificar(calibrado, perfil, pila.coherencia)

    usadas_alta: Arreglo = pila.usadas_en_if_alta(perfil)

    frec: Frecuencias = frecuencias(clasificacion.clases, usadas_alta, perfil)

    if_esperada: Arreglo | None = None

    if auxiliares.elevacion is not None:
        mareas: Arreglo = asarray(
            [
                f.marea_m
                for f, usada in zip(pila.fechas, usadas_alta, strict=True)
                if usada
            ],
            dtype=float64,
        )

        if_esperada = inundacion_esperada(auxiliares.elevacion, mareas, perfil)
        if_esperada[~manglar] = float("nan")

    desconectada: Arreglo = desconexion(
        en_mascara=manglar,
        frecuencias_celda=frec,
        if_esperada=if_esperada,
        perfil=perfil,
        grilla=grilla,
    )

    cambios: Cambios = cambios_previos or detectar_cambios(
        anomalias(calibrado.hv, calibrado.media_hv_por_fecha()),
        manglar,
        perfil,
        semilla,
    )

    resultados_estanques: list[ResultadoEstanque] = (
        []
        if auxiliares.estanques is None
        else evaluar_estanques(
            estanques=auxiliares.estanques,
            hh=calibrado.hh,
            hv=calibrado.hv,
            indice_track=calibrado.indice_track,
            tipica=clasificacion.tipica,
            if_total=frec.if_total,
            manglar=manglar,
            grilla=grilla,
            perfil=perfil,
        )
    )

    grupos: tuple[Arreglo, Arreglo] | None = (
        None
        if auxiliares.barreras is None
        else estratos(
            manglar=manglar,
            suficientes=frec.datos_suficientes,
            barreras=auxiliares.barreras,
            tipica=clasificacion.tipica,
            estanques=auxiliares.estanques,
            elevacion=auxiliares.elevacion,
            grilla=grilla,
        )
    )

    resumen_pais, resumen_fecha = resumir(
        grilla=grilla,
        manglar=manglar,
        desconectada=desconectada,
        suficientes=frec.datos_suficientes,
        perdida=cambios.significativo,
        tipica=clasificacion.tipica,
        clases=clasificacion.clases,
        paises=auxiliares.paises,
        codigos_paises=auxiliares.codigos_paises,
    )

    return Resultado(
        calibrado=calibrado,
        clasificacion=clasificacion,
        frecuencias=frec,
        usadas_alta=usadas_alta,
        humedal=humedal,
        en_mascara=manglar,
        if_esperada=if_esperada,
        desconectada=desconectada,
        cambios=cambios,
        estanques=resultados_estanques,
        hipotesis=probar_hipotesis(
            if_alta=frec.if_alta,
            perdida=cambios.significativo,
            desconectada=desconectada,
            grupos=grupos,
            resultados_estanques=resultados_estanques,
            estanques=auxiliares.estanques,
            grilla=grilla,
        ),
        resumen_pais=resumen_pais,
        resumen_fecha=resumen_fecha,
    )

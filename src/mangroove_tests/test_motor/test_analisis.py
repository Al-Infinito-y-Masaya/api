from dataclasses import replace

from numpy import array_equal, bincount, full, isfinite
from pytest import approx

from mangroove_motor.analisis import Resultado, analizar
from mangroove_motor.datos import Auxiliares
from mangroove_motor.perfil import Clase, Perfil
from mangroove_motor.sintetica import Escena
from mangroove_motor.types import Arreglo
from mangroove_tests.test_motor.conftest import SEMILLA

########################################################################################


def precision_exhaustividad(
    verdad: Arreglo,
    prediccion: Arreglo,
) -> tuple[float, float]:
    aciertos: int = int((verdad & prediccion).sum())

    return aciertos / max(1, int(prediccion.sum())), aciertos / max(
        1, int(verdad.sum())
    )


########################################################################################


def test_classes_match_the_synthetic_truth(
    escena: Escena, resultado: Resultado
) -> None:
    exactitud: float = float(
        (resultado.clasificacion.clases == escena.verdad.clases).mean()
    )

    assert exactitud >= 0.9


def test_every_class_present_in_the_truth_is_recovered(
    escena: Escena,
    resultado: Resultado,
) -> None:
    for clase in (Clase.NI, Clase.IV, Clase.OW):
        celdas = escena.verdad.clases == clase

        assert float((resultado.clasificacion.clases[celdas] == clase).mean()) >= 0.9


def test_disconnection_reaches_the_acceptance_bar(
    escena: Escena,
    resultado: Resultado,
) -> None:
    precision, exhaustividad = precision_exhaustividad(
        escena.verdad.desconectada,
        resultado.desconectada,
    )

    assert precision >= 0.8
    assert exhaustividad >= 0.8


def test_canopy_loss_is_detected_at_its_date(
    escena: Escena, resultado: Resultado
) -> None:
    perdida = resultado.cambios.significativo

    precision, exhaustividad = precision_exhaustividad(escena.verdad.perdida, perdida)

    assert precision >= 0.8
    assert exhaustividad >= 0.8

    detectadas = resultado.cambios.orden[escena.verdad.perdida & perdida]

    assert int(bincount(detectadas).argmax()) == escena.verdad.fecha_perdida
    assert (resultado.cambios.delta_hv_db[perdida] < 0).all()


def test_only_mangrove_cells_get_a_change_result(
    escena: Escena,
    resultado: Resultado,
) -> None:
    fuera = ~escena.auxiliares.manglar

    assert not resultado.cambios.significativo[fuera].any()
    assert not isfinite(resultado.cambios.confianza[fuera]).any()


def test_ponds_are_classified_and_only_abandoned_ones_scored(
    escena: Escena,
    resultado: Resultado,
) -> None:
    for estanque in resultado.estanques:
        assert estanque.activo == escena.verdad.estanques_activos[estanque.numero]
        assert (estanque.puntaje is None) == estanque.activo


def test_hypotheses_follow_the_scene(resultado: Resultado) -> None:
    pruebas = {p.codigo: p for p in resultado.hipotesis}

    assert pruebas["H1"].evaluable
    assert pruebas["H1"].p_valor is not None
    assert pruebas["H1"].p_valor < 0.001
    assert pruebas["H2"].evaluable
    assert not pruebas["H3"].evaluable
    assert pruebas["H3"].motivo


def test_country_summaries_add_up_to_the_region(resultado: Resultado) -> None:
    region, *paises = resultado.resumen_pais

    assert not region.pais
    assert sum(p.ha_manglar for p in paises) == approx(region.ha_manglar)
    assert sum(p.ha_desconectada for p in paises) == approx(region.ha_desconectada)
    assert sum(p.n_celdas for p in paises) == region.n_celdas


def test_daily_summaries_cover_every_date(escena: Escena, resultado: Resultado) -> None:
    ha_manglar: float = (
        float(escena.auxiliares.manglar.sum()) * escena.grilla.hectareas_por_celda
    )

    region = [f for f in resultado.resumen_fecha if not f.pais]

    assert len(region) == escena.pila.t

    for fecha in region:
        total = fecha.ha_iv + fecha.ha_ow + fecha.ha_ni + fecha.ha_nc + fecha.ha_nd

        assert total == approx(ha_manglar)


def test_same_inputs_and_seed_give_the_same_output(escena: Escena) -> None:
    primera = analizar(
        pila=escena.pila,
        auxiliares=escena.auxiliares,
        grilla=escena.grilla,
        perfil=Perfil(),
        semilla=SEMILLA,
    )
    segunda = analizar(
        pila=escena.pila,
        auxiliares=escena.auxiliares,
        grilla=escena.grilla,
        perfil=Perfil(),
        semilla=SEMILLA,
    )

    assert array_equal(primera.clasificacion.clases, segunda.clasificacion.clases)
    assert array_equal(primera.cambios.orden, segunda.cambios.orden)
    assert array_equal(
        primera.cambios.confianza,
        segunda.cambios.confianza,
        equal_nan=True,
    )


def test_previous_changes_are_reused(escena: Escena, resultado: Resultado) -> None:
    otra = analizar(
        pila=escena.pila,
        auxiliares=escena.auxiliares,
        grilla=escena.grilla,
        perfil=replace(Perfil(), if_alta_desconectada=0.5),
        semilla=SEMILLA + 1,
        cambios_previos=resultado.cambios,
    )

    assert otra.cambios is resultado.cambios


def test_without_tide_there_is_no_high_tide_frequency(escena: Escena) -> None:
    pila = replace(
        escena.pila,
        fechas=tuple(replace(f, marea_m=None) for f in escena.pila.fechas),
    )

    resultado = analizar(
        pila=pila,
        auxiliares=escena.auxiliares,
        grilla=escena.grilla,
        perfil=Perfil(),
        semilla=SEMILLA,
    )

    assert not resultado.usadas_alta.any()
    assert not resultado.frecuencias.datos_suficientes.any()
    assert not resultado.desconectada.any()
    assert not isfinite(resultado.frecuencias.if_alta).any()


def test_elevation_feeds_expected_flooding(escena: Escena) -> None:
    cotas = full(escena.grilla.n, 0.2)
    cotas[~escena.auxiliares.manglar] = 3.0

    resultado = analizar(
        pila=escena.pila,
        auxiliares=replace(escena.auxiliares, elevacion=cotas),
        grilla=escena.grilla,
        perfil=replace(Perfil(), usar_elevacion=True),
        semilla=SEMILLA,
    )

    assert resultado.if_esperada is not None
    assert not isfinite(resultado.if_esperada[~escena.auxiliares.manglar]).any()
    assert (resultado.if_esperada[escena.auxiliares.manglar] > 0.9).all()
    assert resultado.desconectada.any()


def test_minimal_inputs_still_produce_a_result(escena: Escena) -> None:
    resultado = analizar(
        pila=escena.pila,
        auxiliares=Auxiliares(manglar=escena.auxiliares.manglar),
        grilla=escena.grilla,
        perfil=Perfil(),
        semilla=SEMILLA,
    )

    assert resultado.estanques == []
    assert [p.evaluable for p in resultado.hipotesis] == [False, False, False]
    assert len(resultado.resumen_pais) == 1

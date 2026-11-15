from dataclasses import replace
from math import log10

from numpy import (
    arange,
    array,
    full,
    isfinite,
    nan,
    ones,
    zeros,
)
from numpy.random import default_rng
from pytest import approx, mark

from mangroove_motor.calibracion import calibrar, elegir_estables, media_lineal
from mangroove_motor.clasificacion import Clasificacion, clase_estatica, clasificar
from mangroove_motor.cusum import SIN_CAMBIO, detectar_cambios, permutaciones
from mangroove_motor.datos import Fecha, Pila
from mangroove_motor.estanques import (
    ResultadoEstanque,
    coeficiente_variacion,
    cv_por_tracks,
    puntuar,
)
from mangroove_motor.grilla import Grilla
from mangroove_motor.hipotesis import (
    Prueba,
    comparar_medianas,
    comparar_proporciones,
    distancia_celdas,
    estratos,
    hipotesis_estanques,
    mann_whitney,
)
from mangroove_motor.metricas import (
    desconexion,
    frecuencias,
    inundacion_esperada,
    voto_mayoria,
)
from mangroove_motor.perfil import (
    Clase,
    NivelMarea,
    Perfil,
    nivel_marea,
    usada_en_if_alta,
)

########################################################################################

PERFIL: Perfil = Perfil()


def grilla(ancho: int, alto: int) -> Grilla:
    return Grilla(epsg=32616, x0=0.0, y0=0.0, celda_m=100.0, ancho=ancho, alto=alto)


########################################################################################


@mark.parametrize(
    ("marea", "nivel"),
    [
        (None, NivelMarea.DESCONOCIDA),
        (0.9, NivelMarea.ALTA),
        (-0.9, NivelMarea.BAJA),
        (0.0, NivelMarea.MEDIA),
    ],
)
def test_tide_levels(marea: float | None, nivel: NivelMarea) -> None:
    assert nivel_marea(PERFIL, marea) == nivel


def test_rain_excludes_a_high_tide_date() -> None:
    assert usada_en_if_alta(PERFIL, 0.9, None)
    assert usada_en_if_alta(PERFIL, 0.9, 10.0)
    assert not usada_en_if_alta(PERFIL, 0.9, 80.0)
    assert not usada_en_if_alta(PERFIL, 0.1, 0.0)


def test_profile_fingerprint_changes_with_any_threshold() -> None:
    assert PERFIL.huella() == Perfil().huella()
    assert PERFIL.huella() != replace(PERFIL, sigma_db=1.0).huella()


########################################################################################


def test_linear_mean_ignores_missing_dates() -> None:
    valores = array([[-10.0, nan], [-20.0, nan]])

    media = media_lineal(valores)

    assert media[0] == approx(10 * log10((0.1 + 0.01) / 2))
    assert not isfinite(media[1])


def test_calibration_removes_separate_hh_and_hv_offsets() -> None:
    generador = default_rng(0)

    hh = -12.0 + 0.1 * generador.standard_normal((6, 500))
    hv = -18.0 + 0.1 * generador.standard_normal((6, 500))

    hh[2] += 1.0
    hv[2] -= 2.0

    calibrado = calibrar(
        hh,
        hv,
        array([1, 1, 1, 2, 2, 2]),
        candidatas=(ones(500, dtype=bool),),
        perfil=PERFIL,
    )

    assert calibrado.desfase_hh[2] - calibrado.desfase_hh[0] == approx(1.0, abs=0.05)
    assert calibrado.desfase_hv[2] - calibrado.desfase_hv[0] == approx(-2.0, abs=0.05)
    assert calibrado.tracks.tolist() == [1, 2]
    assert calibrado.media_hh.shape == (2, 500)
    assert calibrado.n_estables == 500


def test_stable_cells_fall_back_through_the_candidates() -> None:
    utilizables = ones(10, dtype=bool)

    pocas = zeros(10, dtype=bool)
    pocas[0] = True

    muchas = ones(10, dtype=bool)
    muchas[:3] = False

    assert elegir_estables([pocas, muchas], utilizables, 5).sum() == 7
    assert elegir_estables([pocas], utilizables, 5).sum() == 10


########################################################################################


def test_static_rules_pick_water_flooded_vegetation_and_dry() -> None:
    clases = clase_estatica(
        array([-20.0, -4.0, -9.0, nan]), array([-25.0, -11.0, -15.0, -10.0]), PERFIL
    )

    assert clases.tolist() == [Clase.OW, Clase.IV, Clase.NI, Clase.ND]


def classify_one(
    hh: list[float], hv: list[float], coherencia: list[float] | None = None
) -> Clasificacion:
    t: int = len(hh)

    datos_hh = full((t, 500), -12.0)
    datos_hv = full((t, 500), -18.0)

    datos_hh[:, :250] = array([hh]).T
    datos_hv[:, :250] = array([hv]).T

    estables = zeros(500, dtype=bool)
    estables[250:] = True

    calibrado = calibrar(
        datos_hh,
        datos_hv,
        zeros(t, dtype=int),
        candidatas=(estables,),
        perfil=PERFIL,
    )

    coh = None

    if coherencia is not None:
        coh = zeros((t, 500))
        coh[:, :250] = array([coherencia]).T

    return clasificar(calibrado, PERFIL, coh)


def test_change_rules_and_out_of_model_class() -> None:
    clasificacion = classify_one([-9.0, -9.0, -5.5, -0.5], [-16.0, -16.0, -12.0, -5.0])

    assert clasificacion.clases[:, 0].tolist() == [
        Clase.NI,
        Clase.NI,
        Clase.IV,
        Clase.NC,
    ]


def test_flooded_typical_cell_drops_to_dry_on_a_large_hh_fall() -> None:
    clasificacion = classify_one(
        [-4.0, -4.0, -4.0, -10.0], [-12.0, -12.0, -12.0, -12.0]
    )

    assert clasificacion.tipica[0] == Clase.IV
    assert clasificacion.clases[-1, 0] == Clase.NI


def test_coherence_turns_water_into_mudflat() -> None:
    clasificacion = classify_one([-20.0, -20.0], [-26.0, -26.0], [0.9, 0.1])

    assert clasificacion.clases[:, 0].tolist() == [Clase.NI, Clase.OW]


def test_error_probability_is_lower_far_from_thresholds() -> None:
    lejos = classify_one([-30.0, -30.0], [-35.0, -35.0]).p_error[0]
    cerca = classify_one([-16.6, -16.6], [-22.1, -22.1]).p_error[0]

    assert lejos < cerca
    assert 0 <= lejos <= 1


def test_cells_without_data_are_nd_and_have_no_error() -> None:
    clasificacion = classify_one([nan, nan], [nan, nan])

    assert (clasificacion.clases[:, :250] == Clase.ND).all()
    assert (clasificacion.tipica[:250] == Clase.ND).all()
    assert not isfinite(clasificacion.p_error[:250]).any()


########################################################################################


def test_frequencies_count_only_valid_high_tide_dates() -> None:
    clases = array([
        [Clase.IV, Clase.NI],
        [Clase.OW, Clase.ND],
        [Clase.NI, Clase.ND],
        [Clase.IV, Clase.NI],
    ])

    resultado = frecuencias(
        clases, array([True, True, False, True]), Perfil(min_fechas_alta=2)
    )

    assert resultado.n_fechas.tolist() == [4, 2]
    assert resultado.n_fechas_alta.tolist() == [3, 2]
    assert resultado.if_total[0] == approx(0.75)
    assert resultado.if_alta[0] == approx(1.0)
    assert resultado.if_alta[1] == approx(0.0)
    assert resultado.datos_suficientes.tolist() == [True, True]

    insuficientes = frecuencias(clases, array([True, False, False, False]), PERFIL)

    assert not insuficientes.datos_suficientes.any()
    assert not isfinite(insuficientes.if_alta).any()


def test_expected_flooding_compares_tide_with_height() -> None:
    esperada = inundacion_esperada(array([0.1, 0.9, nan]), array([0.6, 1.0]), PERFIL)

    assert esperada[0] == approx(1.0)
    assert esperada[1] == approx(0.5)
    assert not isfinite(esperada[2])
    assert not isfinite(inundacion_esperada(array([0.1]), array([]), PERFIL)).any()


def test_majority_vote_removes_isolated_cells() -> None:
    g = grilla(5, 5)

    marcadas = zeros(25, dtype=bool)
    marcadas[17] = True
    marcadas[:10] = True

    elegibles = ones(25, dtype=bool)

    resultado = voto_mayoria(marcadas, elegibles, g)

    assert not resultado[17]
    assert resultado[:10].all()


def test_disconnection_needs_mask_data_and_expected_flooding() -> None:
    g = grilla(3, 1)

    clases = array([[Clase.NI, Clase.NI, Clase.IV]] * 4)

    frec = frecuencias(clases, ones(4, dtype=bool), PERFIL)

    mascara = array([True, True, True])

    sin_mayoria = Perfil(mayoria=False, usar_elevacion=True)

    resultado = desconexion(
        en_mascara=mascara,
        frecuencias_celda=frec,
        if_esperada=array([0.9, 0.1, 0.9]),
        perfil=sin_mayoria,
        grilla=g,
    )

    assert resultado.tolist() == [True, False, False]


########################################################################################


def test_cusum_finds_a_drop_with_high_confidence() -> None:
    generador = default_rng(1)

    serie = 0.2 * generador.standard_normal((20, 50))
    serie[12:, :25] -= 3.0

    cambios = detectar_cambios(serie, ones(50, dtype=bool), PERFIL, 42)

    assert (cambios.orden[:25] == 12).mean() > 0.9
    assert cambios.significativo[:25].all()
    assert not cambios.significativo[25:].any()


def test_cusum_runs_on_each_cells_available_dates() -> None:
    serie = zeros((10, 2))
    serie[6:, :] = -4.0
    serie[0:2, 1] = nan

    cambios = detectar_cambios(serie, ones(2, dtype=bool), PERFIL, 3)

    assert cambios.orden.tolist() == [6, 6]


def test_cusum_skips_cells_with_too_few_dates() -> None:
    serie = full((5, 1), nan)
    serie[:3, 0] = [1.0, 2.0, 3.0]

    cambios = detectar_cambios(serie, ones(1, dtype=bool), PERFIL, 3)

    assert cambios.orden[0] == SIN_CAMBIO
    assert not cambios.significativo.any()

    vacias = detectar_cambios(zeros((3, 4)), ones(4, dtype=bool), PERFIL, 3)

    assert (vacias.orden == SIN_CAMBIO).all()


def test_permutations_are_seeded_per_length() -> None:
    assert (permutaciones(5, 3, 9) == permutaciones(5, 3, 9)).all()
    assert permutaciones(5, 3, 9).shape == (3, 5)


########################################################################################


def test_coefficient_of_variation_and_per_track_average() -> None:
    assert coeficiente_variacion(array([1.0, 1.0, 1.0])) == approx(0.0)
    assert not isfinite(coeficiente_variacion(array([1.0])))
    assert not isfinite(coeficiente_variacion(array([-1.0, -1.0])))

    serie = array([1.0, 3.0, 2.0, 2.0])

    assert cv_por_tracks(serie, array([0, 0, 1, 1])) == approx(0.25)
    assert not isfinite(cv_por_tracks(array([1.0, nan]), array([0, 1])))


def test_abandoned_ponds_without_a_channel_score_without_distance() -> None:
    lejano = ResultadoEstanque(
        numero=1,
        n_celdas=4,
        area_ha=4.0,
        cv_hh=0.1,
        cv_hv=0.1,
        cv=0.1,
        activo=False,
        dist_canal_km=float("inf"),
        if_vecino=None,
        puntaje=None,
    )

    (puntuado,) = puntuar([lejano], PERFIL)

    assert puntuado.puntaje == approx(PERFIL.puntaje_area)


########################################################################################


def test_mann_whitney_matches_a_clear_separation() -> None:
    u, z, p, r = mann_whitney(arange(10.0), arange(10.0) + 20)

    assert u == approx(0.0)
    assert z < 0
    assert p < 0.001
    assert r < 0


def test_small_groups_are_not_evaluable() -> None:
    medianas = comparar_medianas("H1", ("a", "b"), array([1.0, nan]), arange(10.0))
    proporciones = comparar_proporciones(
        "H2", ("a", "b"), array([True]), ones(10, dtype=bool)
    )

    assert not medianas.evaluable
    assert medianas.n_a == 1
    assert not proporciones.evaluable
    assert proporciones.prueba == Prueba.FISHER


def test_fisher_compares_loss_proportions() -> None:
    a = array([True] * 9 + [False])
    b = array([False] * 9 + [True])

    resultado = comparar_proporciones("H2", ("a", "b"), a, b)

    assert resultado.evaluable
    assert resultado.p_valor is not None
    assert resultado.p_valor < 0.01
    assert resultado.efecto == approx(0.8)


def test_strata_need_barriers_and_match_heights() -> None:
    g = grilla(10, 1)

    base = {
        "estanques": None,
        "grilla": g,
        "manglar": ones(10, dtype=bool),
        "suficientes": ones(10, dtype=bool),
        "tipica": array([Clase.OW] + [Clase.NI] * 9),
    }

    assert estratos(barreras=zeros(10), elevacion=None, **base) is None

    barreras = zeros(10)
    barreras[9] = 1

    grupos = estratos(barreras=barreras, elevacion=ones(10), **base)

    assert grupos is not None

    a, b = grupos

    assert a.any()
    assert b.any()


def test_distances_are_infinite_without_targets() -> None:
    assert not isfinite(distancia_celdas(zeros(4, dtype=bool), grilla(2, 2))).any()


def test_pond_hypothesis_without_ponds_is_not_evaluable() -> None:
    resultado = hipotesis_estanques([], None, zeros(4, dtype=bool), grilla(2, 2))

    assert not resultado.evaluable


def test_dates_build_the_stack_metadata() -> None:
    pila = Pila(
        hh=zeros((2, 1)),
        hv=zeros((2, 1)),
        fechas=(Fecha(track=1, marea_m=1.0), Fecha(track=2)),
    )

    assert pila.t == 2
    assert pila.tracks.tolist() == [1, 2]
    assert pila.usadas_en_if_alta(PERFIL).tolist() == [True, False]

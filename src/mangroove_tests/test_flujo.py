from dataclasses import replace
from datetime import timedelta
from json import dumps
from pathlib import Path
from types import SimpleNamespace

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import Client
from django.utils.timezone import now
from numpy import full_like, nan, zeros_like
from pytest import fixture, mark, raises

from api_auth.models import ApiUser
from mangroove_adquisiciones.enums import EstadoRecorte
from mangroove_adquisiciones.models import Adquisicion, Recorte, Sincronizacion
from mangroove_adquisiciones.services import SincronizacionEnCursoError, sincronizar
from mangroove_analisis.enums import EstadoCorrida
from mangroove_analisis.models import Corrida, CorridaFecha, ResultadoCelda
from mangroove_analisis.services import (
    CorridaInvalidaError,
    crear_corrida,
    ejecutar_corrida,
    ejecutar_pendientes,
    proponer_corrida,
)
from mangroove_insumos.enums import TipoInsumo, TipoSerie
from mangroove_insumos.models import EstimacionMarea, Insumo
from mangroove_insumos.services import cargar_insumo, cargar_serie
from mangroove_motor.sintetica import Escena, generar
from mangroove_publicacion.models import Artefacto
from mangroove_publicacion.relato import RelatoError, lugar, relato, restauracion, ritmo
from mangroove_publicacion.services import (
    matrices,
    proponer_relato,
    publicar,
    purgar_corridas,
    retirar,
)
from mangroove_regiones.models import Region
from mangroove_regiones.services import crear_region
from mangroove_tests.escenario import Nasa, fecha_inicio, instante

########################################################################################

FECHAS: int = 9

########################################################################################


@fixture(scope="module")
def escena() -> Escena:
    return generar()


def poligono(escena: Escena, margen: float) -> dict:
    g = escena.grilla

    oeste, sur, este, norte = g.limites()

    xs = [oeste + margen, este - margen, este - margen, oeste + margen, oeste + margen]
    ys = [norte - margen, norte - margen, sur + margen, sur + margen, norte - margen]

    lon, lat = g.lonlat(xs, ys)  # ty: ignore[invalid-argument-type]

    return {
        "coordinates": [list(zip(lon.tolist(), lat.tolist(), strict=True))],
        "type": "Polygon",
    }


def caracteristica(geometria: dict, propiedades: dict) -> dict:
    return {"geometry": geometria, "properties": propiedades, "type": "Feature"}


@fixture
def region(semillas: None, escena: Escena) -> Region:
    return crear_region(
        codigo="sintetica",
        nombre="Escena sintética",
        aoi=dumps(poligono(escena, 300.0)),
        marea=(-87.2, 12.9),
    )


@fixture
def nasa(escena: Escena) -> Nasa:
    return Nasa(escena=escena, fechas=FECHAS)


@fixture
def sincronizada(region: Region, nasa: Nasa) -> Region:
    sincronizar(
        region,
        desde=fecha_inicio(),
        hasta=fecha_inicio() + timedelta(days=60),
        buscador=nasa.productos,
        apertura=nasa.apertura,  # ty: ignore[invalid-argument-type]
    )

    return region


@fixture
def con_insumos(
    sincronizada: Region, escena: Escena, operador: ApiUser, tmp_path: Path
) -> Region:
    manglar = tmp_path / "manglar.geojson"
    manglar.write_text(
        dumps({
            "features": [caracteristica(poligono(escena, 1500.0), {})],
            "type": "FeatureCollection",
        }),
        encoding="utf-8",
    )

    paises = tmp_path / "paises.geojson"
    paises.write_text(
        dumps({
            "features": [caracteristica(poligono(escena, 0.0), {"iso": "NI"})],
            "type": "FeatureCollection",
        }),
        encoding="utf-8",
    )

    for tipo, archivo in ((TipoInsumo.MANGLAR, manglar), (TipoInsumo.PAISES, paises)):
        cargar_insumo(
            region=sincronizada,
            tipo=tipo,
            ruta=archivo,
            fuente="prueba",
            licencia="CC-BY-4.0",
            usuario=operador,
        )

    mareas = tmp_path / "mareas.csv"
    mareas.write_text(
        "datetime,tide_m\n"
        + "".join(
            f"{(instante(t) + timedelta(hours=h)).isoformat()},"
            f"{escena.pila.fechas[t].marea_m}\n"
            for t in range(FECHAS)
            for h in (-1, 1)
        ),
        encoding="utf-8",
    )

    cargar_serie(
        region=sincronizada,
        tipo=TipoSerie.MAREA,
        ruta=mareas,
        fuente="prueba",
        usuario=operador,
    )

    return sincronizada


def modelo_serie(region: Region) -> str:
    return EstimacionMarea.objects.filter(adquisicion__region=region).values_list(
        "modelo", flat=True
    )[0]


@fixture
def completada(con_insumos: Region) -> Corrida:
    corrida = crear_corrida(
        con_insumos, madurez="provisional", modelo_marea=modelo_serie(con_insumos)
    )

    return ejecutar_corrida(corrida)


@fixture
def publicada(completada: Corrida, operador: ApiUser) -> Corrida:
    return publicar(completada, operador)


########################################################################################


def test_region_freezes_its_grid_and_creates_cells(region: Region) -> None:
    assert region.epsg == 32616
    assert region.celdas.count() == region.n_celdas  # ty: ignore[unresolved-attribute]

    primera = region.celdas.order_by("fila", "columna").first()  # ty: ignore[unresolved-attribute]

    assert primera is not None
    assert primera.codigo == region.grilla().codigo(0, 0)

    region.celda_m = 50  # ty: ignore[invalid-assignment]

    with raises(DatabaseError):
        region.save()


def test_sync_crops_and_consolidates_every_pass(sincronizada: Region) -> None:
    assert Adquisicion.objects.filter(region=sincronizada).count() == FECHAS
    assert (
        Recorte.objects.filter(
            region=sincronizada, estado=EstadoRecorte.RECORTADO
        ).count()
        == FECHAS
    )

    sincronizacion = Sincronizacion.objects.get(region=sincronizada)

    assert sincronizacion.n_encontrados == FECHAS
    assert sincronizacion.n_recortados == FECHAS

    adquisicion = Adquisicion.objects.filter(region=sincronizada).first()

    assert adquisicion is not None
    assert adquisicion.cobertura > 0.9
    assert adquisicion.fecha_codigo.endswith(adquisicion.orbita)


def test_second_sync_brings_nothing_new(sincronizada: Region, nasa: Nasa) -> None:
    segunda = sincronizar(
        sincronizada,
        desde=fecha_inicio(),
        hasta=fecha_inicio(),
        buscador=nasa.productos,
        apertura=nasa.apertura,  # ty: ignore[invalid-argument-type]
    )

    assert segunda.n_recortados == 0
    assert Adquisicion.objects.filter(region=sincronizada).count() == FECHAS


def test_reprocessed_pass_replaces_the_old_one(
    sincronizada: Region, nasa: Nasa
) -> None:
    nasa.crids = {0: "P05036"}

    sincronizar(
        sincronizada,
        desde=fecha_inicio(),
        hasta=fecha_inicio(),
        buscador=nasa.productos,
        apertura=nasa.apertura,  # ty: ignore[invalid-argument-type]
    )

    vigentes = Adquisicion.objects.filter(region=sincronizada, reemplazada=False)

    assert vigentes.count() == FECHAS
    assert (
        Adquisicion.objects.filter(region=sincronizada, reemplazada=True).count() == 1
    )
    assert vigentes.filter(crid="P05036", reemplaza_a__isnull=False).exists()


def test_failed_crops_are_kept_for_retry(region: Region, nasa: Nasa) -> None:
    def falla() -> object:
        def abrir(producto: object) -> object:
            raise OSError("corte de red")

        return abrir

    sincronizar(
        region,
        desde=fecha_inicio(),
        hasta=fecha_inicio(),
        buscador=nasa.productos,
        apertura=falla,  # ty: ignore[invalid-argument-type]
    )

    assert (
        Recorte.objects.filter(
            region=region, estado=EstadoRecorte.FALLIDO, intentos=1
        ).count()
        == FECHAS
    )
    assert not Adquisicion.objects.filter(region=region).exists()


def test_concurrent_syncs_are_rejected(region: Region, nasa: Nasa) -> None:
    Sincronizacion.objects.create(region=region, origen="programada")

    with raises(SincronizacionEnCursoError):
        sincronizar(
            region, desde=fecha_inicio(), hasta=fecha_inicio(), buscador=nasa.productos
        )


def test_inputs_are_versioned_and_deduplicated(
    con_insumos: Region, operador: ApiUser
) -> None:
    insumo = Insumo.objects.get(region=con_insumos, tipo=TipoInsumo.MANGLAR)

    assert insumo.version == 1
    assert insumo.grilla_archivo


def test_run_writes_one_result_per_cell(completada: Corrida) -> None:
    assert completada.estado == EstadoCorrida.COMPLETADA
    assert completada.cubo_archivo
    assert (
        ResultadoCelda.objects.filter(corrida=completada).count()
        == completada.region.n_celdas  # ty: ignore[unresolved-attribute]
    )
    assert CorridaFecha.objects.filter(corrida=completada).count() == FECHAS
    assert CorridaFecha.objects.filter(
        corrida=completada, usada_en_if_alta=True
    ).exists()
    assert ResultadoCelda.objects.filter(corrida=completada, en_mascara=True).exists()
    assert completada.resumen_paises.filter(pais="NI").exists()  # ty: ignore[unresolved-attribute]
    assert completada.hipotesis.count() == 3  # ty: ignore[unresolved-attribute]


def test_results_cannot_be_edited(completada: Corrida) -> None:
    resultado = ResultadoCelda.objects.filter(corrida=completada).first()

    assert resultado is not None

    resultado.pais = "HN"

    with raises(DatabaseError):
        resultado.save()


def test_a_run_needs_current_acquisitions(region: Region) -> None:
    with raises(CorridaInvalidaError):
        crear_corrida(region, madurez="provisional")

    with raises(CorridaInvalidaError):
        crear_corrida(region, madurez="beta")


def test_versions_follow_changes(con_insumos: Region) -> None:
    primera = crear_corrida(con_insumos, madurez="provisional")
    segunda = crear_corrida(con_insumos, madurez="provisional")
    tercera = crear_corrida(con_insumos, madurez="provisional", tracks=[33])

    assert primera.version == "1.0.0"
    assert segunda.version == "1.0.1"
    assert tercera.version == "1.1.0"


def test_worker_runs_pending_runs_and_proposal_skips_duplicates(
    con_insumos: Region,
) -> None:
    propuesta = proponer_corrida(con_insumos)

    assert propuesta is not None
    assert proponer_corrida(con_insumos) is None
    assert ejecutar_pendientes() == 1

    propuesta.refresh_from_db()

    assert propuesta.estado == EstadoCorrida.COMPLETADA


def test_publishing_uploads_layers_and_marks_current(publicada: Corrida) -> None:
    assert publicada.estado == EstadoCorrida.PUBLICADA
    assert publicada.vigente
    assert Artefacto.objects.filter(corrida=publicada, tipo="rgb").count() == FECHAS
    assert Artefacto.objects.filter(corrida=publicada, tipo="manifiesto").exists()
    assert (
        Artefacto.objects.filter(corrida=publicada, formato="png").first().oeste
        is not None
    )


def test_retiring_the_only_published_run_is_refused(publicada: Corrida) -> None:
    with raises(DatabaseError):
        retirar(publicada, "error de prueba")


########################################################################################


@mark.usefixtures("cache_local")
def test_public_api_serves_the_published_version(publicada: Corrida) -> None:
    cliente = Client()

    base = f"/regiones/{publicada.region.codigo}/versiones/{publicada.version}"  # ty: ignore[unresolved-attribute]

    regiones = cliente.get("/regiones/")

    assert regiones.status_code == 200
    assert regiones.json()[0]["version"] == publicada.version

    redireccion = cliente.get(f"/regiones/{publicada.region.codigo}/manifest/")  # ty: ignore[unresolved-attribute]

    assert redireccion.status_code == 307
    assert redireccion["Location"] == f"{base}/manifest/"

    manifiesto = cliente.get(f"{base}/manifest/")

    assert manifiesto.status_code == 200
    assert "immutable" in manifiesto["Cache-Control"]
    assert len(manifiesto.json()["fechas"]) == FECHAS

    repetido = cliente.get(f"{base}/manifest/", HTTP_IF_NONE_MATCH=manifiesto["ETag"])

    assert repetido.status_code == 304

    fecha = manifiesto.json()["fechas"][0]["id"]

    for enlace in (
        manifiesto.json()["fechas"][0]["capas"]["rgb"],
        manifiesto.json()["capas"]["if_alta"],
    ):
        assert cliente.get("/" + enlace).status_code == 302

    assert cliente.get(f"{base}/fechas/{fecha}/capas/rgb/").status_code == 302
    assert cliente.get(f"{base}/capas/desconexion/").status_code == 302

    region = publicada.region
    codigo = region.grilla().codigo(10, 10)  # ty: ignore[unresolved-attribute]

    celda = cliente.get(f"{base}/celdas/{codigo}/")

    assert celda.status_code == 200
    assert len(celda.json()["serie"]) == FECHAS

    lon, lat = region.grilla().lonlat(*region.grilla().centro(10, 10))  # ty: ignore[unresolved-attribute]

    punto = cliente.get(f"{base}/celdas/", {"lat": float(lat), "lon": float(lon)})

    assert punto.json()["id"] == codigo
    assert cliente.get(f"{base}/celdas/", {"lat": 0.0, "lon": 0.0}).status_code == 404
    assert cliente.get(f"{base}/celdas/c_1_2/").status_code == 404

    assert cliente.get(f"{base}/resumen/").json()["paises"]
    assert cliente.get(f"{base}/resumen/", {"formato": "csv"}).status_code == 302
    assert len(cliente.get(f"{base}/hipotesis/").json()) == 3
    assert cliente.get(f"{base}/metodo/").json()["productos"]
    assert cliente.get(f"{base}/descargas/").json()
    assert cliente.get(f"{base}/estanques/").json() == []

    exploracion = cliente.post(
        f"{base}/exploraciones/",
        {"if_alta_desconectada": 0.5},
        content_type="application/json",
    )

    assert exploracion.status_code == 200
    assert exploracion.json()["exploracion"] is True

    capa = cliente.get("/" + exploracion.json()["capas"]["desconexion"])

    assert capa.status_code == 200
    assert capa["Content-Type"] == "image/png"

    assert (
        cliente.get(f"{base}/exploraciones/{'0' * 64}/capas/desconexion/").status_code
        == 404
    )
    assert cliente.get("/regiones/sin_region/manifest/").status_code == 404
    assert (
        cliente.get(f"/regiones/{region.codigo}/versiones/9.9.9/manifest/").status_code  # ty: ignore[unresolved-attribute]
        == 404
    )


@mark.usefixtures("cache_local")
def test_retired_versions_answer_gone_and_are_purged(
    publicada: Corrida, operador: ApiUser
) -> None:
    segunda = ejecutar_corrida(
        crear_corrida(publicada.region, madurez="provisional", tracks=[33, 98]),
    )

    publicar(segunda, operador)

    retirada = retirar(publicada, "reemplazada por una versión más completa")

    segunda.refresh_from_db()

    assert segunda.vigente
    assert retirada.estado == EstadoCorrida.RETIRADA

    respuesta = Client().get(
        f"/regiones/{publicada.region.codigo}/versiones/{publicada.version}/manifest/",  # ty: ignore[unresolved-attribute]
    )

    assert respuesta.status_code == 410

    Corrida.objects.filter(id=publicada.id).update(
        purgar_despues_de=now() - timedelta(days=1)
    )

    assert purgar_corridas() == 1
    assert not ResultadoCelda.objects.filter(corrida=publicada).exists()
    assert not Artefacto.objects.filter(corrida=publicada).exists()


########################################################################################


@mark.usefixtures("cache_local")
def test_tour_scenes_are_published_and_linked(
    publicada: Corrida, operador: ApiUser
) -> None:
    codigo = publicada.region.codigo  # ty: ignore[unresolved-attribute]
    base = f"/regiones/{codigo}/versiones/{publicada.version}"

    cliente = Client()

    assert cliente.get(f"{base}/relato/").status_code == 404
    assert cliente.get(f"{base}/manifest/").json()["relato"] is None

    call_command("proponerrelato", codigo, publicada.version, "--por", operador.email)

    assert Artefacto.objects.filter(corrida=publicada, tipo="relato").exists()
    assert cliente.get(f"{base}/relato/").status_code == 302
    assert cliente.get(f"{base}/manifest/").json()["relato"] == f"{base[1:]}/relato/"

    with raises(CommandError, match="ya tiene relato"):
        call_command(
            "proponerrelato", codigo, publicada.version, "--por", operador.email
        )

    with raises(CommandError, match="no tiene la versión"):
        call_command("proponerrelato", codigo, "9.9.9", "--por", operador.email)


def test_tour_picks_one_scene_per_act(publicada: Corrida) -> None:
    grilla = publicada.region.grilla()  # ty: ignore[unresolved-attribute]

    escenas = relato(publicada, matrices(publicada, grilla))["escenas"]

    assert [e["id"] for e in escenas] == [
        "lugar",
        "ritmo",
        "desconexion",
        "parche",
        "incertidumbre",
    ]

    ritmo_escena = escenas[1]

    assert len(ritmo_escena["fechas"]) == 2
    assert ritmo_escena["datos"]["marea_m"][0] < ritmo_escena["datos"]["marea_m"][1]
    assert escenas[2]["datos"]["n_celdas"] > 0
    assert grilla.celda_de_codigo(escenas[3]["celdas"][0]) is not None
    assert escenas[4]["celdas"] == escenas[3]["celdas"]


def test_tour_names_the_act_without_data(publicada: Corrida, operador: ApiUser) -> None:
    grilla = publicada.region.grilla()  # ty: ignore[unresolved-attribute]

    m = matrices(publicada, grilla)

    with raises(RelatoError, match="desconexion"):
        relato(publicada, replace(m, desconectada=zeros_like(m.desconectada)))

    with raises(RelatoError, match="parche"):
        relato(publicada, replace(m, suficientes=zeros_like(m.suficientes)))

    with raises(RelatoError, match="lugar"):
        lugar([], publicada.region)  # ty: ignore[invalid-argument-type]

    sin_marea = list(publicada.fechas.select_related("adquisicion"))  # ty: ignore[unresolved-attribute]

    for f in sin_marea:
        f.marea_m = None

    with raises(RelatoError, match="ritmo"):
        ritmo(sin_marea, publicada.region)  # ty: ignore[invalid-argument-type]

    vacio = replace(m, p_error=full_like(m.p_error, nan))

    with raises(RelatoError, match="incertidumbre"):
        relato(publicada, vacio)

    with raises(CorridaInvalidaError):
        proponer_relato(
            crear_corrida(publicada.region, madurez="provisional", tracks=[33, 98]),
            operador,
        )


class Consulta:
    def __init__(self, fila: object) -> None:
        self.fila = fila

    def select_related(self, *_: str) -> Consulta:
        return self

    def filter(self, **_: object) -> Consulta:
        return self

    def order_by(self, *_: str) -> Consulta:
        return self

    def first(self) -> object:
        return self.fila


def test_restoration_scene_centres_the_best_abandoned_pond() -> None:
    anillo = [[-87.0, 13.0], [-86.0, 13.0], [-86.0, 14.0], [-87.0, 14.0]]

    estanque = SimpleNamespace(
        codigo="e1",
        geometria={"coordinates": [[anillo]], "type": "MultiPolygon"},
    )

    corrida = SimpleNamespace(
        estanques=Consulta(
            SimpleNamespace(estanque=estanque, puntaje=0.8, area_ha=12.0)
        ),
    )

    escena_final = restauracion(corrida)  # ty: ignore[invalid-argument-type]

    assert escena_final is not None
    assert escena_final["centro"] == [-86.5, 13.5]
    assert escena_final["datos"]["estanque"] == "e1"
    assert restauracion(SimpleNamespace(estanques=Consulta(None))) is None  # ty: ignore[invalid-argument-type]

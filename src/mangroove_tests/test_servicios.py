from datetime import UTC, date, datetime, timedelta
from io import BytesIO, StringIO
from json import dumps
from pathlib import Path
from types import SimpleNamespace

from django.core.management import call_command
from django.core.management.base import CommandError
from h5py import File
from numpy import arange, array, float32, full, nan, ones
from numpy.ma import masked_array
from pydantic import SecretStr
from pytest import MonkeyPatch, approx, fixture, raises
from rasterio import open as abrir_raster
from rasterio.transform import from_origin

from api_auth.models import ApiUser
from api_media.enums import MediaVisibility
from mangroove_adquisiciones import services as adquisiciones
from mangroove_adquisiciones.enums import Madurez
from mangroove_adquisiciones.models import Adquisicion, Producto, Recorte
from mangroove_comun.comandos import (
    corrida_por_id,
    fecha,
    region_por_codigo,
    usuario_por_identificador,
)
from mangroove_comun.config import MangrooveConfig
from mangroove_comun.medios import AlmacenamientoError, dimensiones, subir
from mangroove_insumos import services as insumos
from mangroove_insumos.enums import TipoInsumo, TipoSerie
from mangroove_insumos.models import Insumo, LluviaDiaria
from mangroove_insumos.services import (
    InsumoInvalidoError,
    cargar_insumo,
    cargar_serie,
    estimar_mareas,
    lluvia_3d,
    obtener_lluvia,
    precipitacion_media,
)
from mangroove_motor import marea
from mangroove_motor.marea import alturas_marea, interpolar_serie
from mangroove_regiones.models import Region
from mangroove_regiones.services import crear_region
from mangroove_tests.escenario import ArchivoFalso, granulo
from mangroove_tests.test_motor.gcov import escribir_gcov

########################################################################################

AOI: str = "POLYGON((-87.40 12.80,-87.39 12.80,-87.39 12.81,-87.40 12.81,-87.40 12.80))"


@fixture
def region(db: None) -> Region:
    return crear_region(
        codigo="chica", nombre="Región chica", aoi=AOI, marea=(-87.4, 12.8)
    )


def raster(
    ruta: Path, region: Region, valores: float, *, cobertura: float = 1.0
) -> Path:
    g = region.grilla()

    ancho: int = int(g.ancho * 2 * cobertura) or 1

    with abrir_raster(
        ruta,
        "w",
        count=1,
        crs=g.crs,
        driver="GTiff",
        dtype="float32",
        height=g.alto * 2,
        transform=from_origin(g.x0, g.y0, g.celda_m / 2, g.celda_m / 2),
        width=ancho,
    ) as salida:
        salida.write(full((g.alto * 2, ancho), valores, dtype=float32), 1)

    return ruta


########################################################################################


def test_raster_inputs_are_reprojected_and_versioned(
    region: Region,
    operador: ApiUser,
    tmp_path: Path,
) -> None:
    dem = cargar_insumo(
        region=region,
        tipo=TipoInsumo.ELEVACION,
        ruta=raster(tmp_path / "dem.tif", region, 2.5),
        fuente="Copernicus GLO-30",
        licencia="CC-BY-4.0",
        usuario=operador,
    )

    otra = cargar_insumo(
        region=region,
        tipo=TipoInsumo.ELEVACION,
        ruta=raster(tmp_path / "dem2.tif", region, 3.0),
        fuente="Copernicus GLO-30",
        licencia="CC-BY-4.0",
        usuario=operador,
    )

    repetida = cargar_insumo(
        region=region,
        tipo=TipoInsumo.ELEVACION,
        ruta=tmp_path / "dem.tif",
        fuente="Copernicus GLO-30",
        licencia="CC-BY-4.0",
        usuario=operador,
    )

    assert (dem.version, otra.version) == (1, 2)
    assert repetida.id == dem.id
    assert dem.formato == "raster"


def test_invalid_inputs_are_rejected(
    region: Region, operador: ApiUser, tmp_path: Path
) -> None:
    base: dict = {
        "fuente": "x",
        "licencia": "CC-BY-4.0",
        "region": region,
        "usuario": operador,
    }

    with raises(InsumoInvalidoError):
        cargar_insumo(tipo=TipoInsumo.MANGLAR, ruta=tmp_path / "a.shp", **base)

    with raises(InsumoInvalidoError):
        cargar_insumo(
            tipo=TipoInsumo.BARRERAS,
            ruta=raster(tmp_path / "b.tif", region, 1.0),
            **base,
        )

    with raises(InsumoInvalidoError):
        cargar_insumo(
            tipo=TipoInsumo.ELEVACION,
            ruta=raster(tmp_path / "c.tif", region, 1.0, cobertura=0.2),
            **base,
        )

    lineal = tmp_path / "d.geojson"
    lineal.write_text(
        dumps({"coordinates": [[0, 0], [1, 1]], "type": "LineString"}), encoding="utf-8"
    )

    with raises(InsumoInvalidoError):
        cargar_insumo(tipo=TipoInsumo.ELEVACION, ruta=lineal, **base)


def test_vector_inputs_create_ponds_and_barriers(
    region: Region,
    operador: ApiUser,
    tmp_path: Path,
) -> None:
    poligono = {
        "coordinates": [
            [
                [-87.399, 12.801],
                [-87.395, 12.801],
                [-87.395, 12.805],
                [-87.399, 12.805],
                [-87.399, 12.801],
            ]
        ],
        "type": "Polygon",
    }

    for tipo in (
        TipoInsumo.ESTANQUES,
        TipoInsumo.BARRERAS,
        TipoInsumo.AREAS_PROTEGIDAS,
        TipoInsumo.EXCLUSION,
    ):
        ruta = tmp_path / f"{tipo}.geojson"
        ruta.write_text(
            dumps({
                "features": [
                    {
                        "geometry": poligono,
                        "properties": {"id": "E1"},
                        "type": "Feature",
                    }
                ],
                "type": "FeatureCollection",
            }),
            encoding="utf-8",
        )

        insumo = cargar_insumo(
            region=region,
            tipo=tipo,
            ruta=ruta,
            fuente="x",
            licencia="ODbL-1.0",
            usuario=operador,
        )

        assert insumo.formato == "vector"

    estanques = Insumo.objects.get(
        region=region, tipo=TipoInsumo.ESTANQUES
    ).estanques.all()

    assert [e.codigo for e in estanques] == ["E1"]
    assert estanques[0].area_ha > 0
    assert not Insumo.objects.get(
        region=region,
        tipo=TipoInsumo.AREAS_PROTEGIDAS,
    ).grilla_archivo


def test_series_validate_columns_and_load_rain(
    region: Region, operador: ApiUser, tmp_path: Path
) -> None:
    mala = tmp_path / "mala.csv"
    mala.write_text("fecha,valor\n2026-01-01,1\n", encoding="utf-8")

    with raises(InsumoInvalidoError):
        cargar_serie(
            region=region,
            tipo=TipoSerie.LLUVIA,
            ruta=mala,
            fuente="x",
            usuario=operador,
        )

    lluvia = tmp_path / "lluvia.csv"
    lluvia.write_text(
        "date,rain_mm\n2026-07-01,5\n2026-07-02,10\n2026-07-03,20\n", encoding="utf-8"
    )

    serie = cargar_serie(
        region=region,
        tipo=TipoSerie.LLUVIA,
        ruta=lluvia,
        fuente="estación",
        usuario=operador,
    )

    fuente = f"serie:{serie.id}"

    instante = datetime(2026, 7, 3, 18, tzinfo=UTC)

    assert lluvia_3d(region, instante, fuente) == approx(35.0)
    assert lluvia_3d(region, instante + timedelta(days=1), fuente) is None
    assert lluvia_3d(region, instante, "") is None


def test_tide_estimation_uses_the_configured_model(
    region: Region,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    adquisicion = Adquisicion.objects.create(
        region=region,
        track=33,
        orbita="asc",
        frames=[8],
        inicio_at=datetime(2026, 7, 3, 11, 22, tzinfo=UTC),
        madurez=Madurez.PROVISIONAL,
        crid="P05023",
        cobertura=1.0,
    )

    assert estimar_mareas(region, [adquisicion]) == 0

    monkeypatch.setattr(insumos.MANGROOVE_CONFIG, "MANGROOVE_MAREA", tmp_path)
    monkeypatch.setattr(
        insumos, "alturas_marea", lambda instantes, **_: [0.8 for _ in instantes]
    )

    assert estimar_mareas(region, [adquisicion]) == 1
    assert estimar_mareas(region, [adquisicion]) == 0


def test_pytmd_results_are_masked_to_none(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:

    monkeypatch.setattr(
        marea,
        "tide_elevations",
        lambda *a, **k: masked_array([0.5, 9.0], mask=[False, True]),
    )

    instantes = [datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 2, tzinfo=UTC)]

    assert alturas_marea(
        instantes, lon=0.0, lat=0.0, directorio=tmp_path, modelo="GOT4.10_nc"
    ) == [0.5, None]
    assert (
        alturas_marea([], lon=0.0, lat=0.0, directorio=tmp_path, modelo="GOT4.10_nc")
        == []
    )


def test_pytmd_arrays_drop_non_finite_values(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        marea, "tide_elevations", lambda *a, **k: array([[0.25], [nan]])
    )

    instantes = [datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 2, tzinfo=UTC)]

    assert alturas_marea(
        instantes, lon=0.0, lat=0.0, directorio=tmp_path, modelo="GOT4.10_nc"
    ) == [0.25, None]


def test_empty_tide_directory_means_no_model(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("MANGROOVE_MAREA", "")

    assert MangrooveConfig().MANGROOVE_MAREA is None


def test_series_interpolate_inside_their_range() -> None:
    t0 = datetime(2026, 7, 1, tzinfo=UTC)

    serie = [(t0, 0.0), (t0 + timedelta(hours=2), 1.0), (t0 + timedelta(hours=2), 1.0)]

    assert interpolar_serie(
        [t0 + timedelta(hours=1), t0 - timedelta(hours=1)], serie
    ) == [0.5, None]


def test_imerg_rain_is_averaged_over_the_region(
    region: Region,
    monkeypatch: MonkeyPatch,
) -> None:
    contenido = BytesIO()

    with File(contenido, "w") as h5:
        grupo = h5.create_group("Grid")
        grupo.create_dataset("lat", data=arange(12.75, 12.86, 0.1))
        grupo.create_dataset("lon", data=arange(-87.45, -87.34, 0.1))
        grupo.create_dataset("precipitation", data=full((1, 2, 2), 4.0, dtype=float32))

    resultado = {
        "umm": {
            "TemporalExtent": {
                "RangeDateTime": {"BeginningDateTime": "2026-07-01T00:00:00Z"}
            }
        }
    }

    monkeypatch.setattr(insumos, "login", lambda **_: None)
    monkeypatch.setattr(insumos, "search_data", lambda **_: [resultado, resultado])
    monkeypatch.setattr(
        insumos,
        "abrir",
        lambda resultados: [
            BytesIO(contenido.getvalue()),
            BytesIO(contenido.getvalue()),
        ],
    )

    assert obtener_lluvia(region, desde=date(2026, 7, 1), hasta=date(2026, 7, 1)) == 1
    assert LluviaDiaria.objects.get(region=region).mm == approx(4.0)

    vacio = BytesIO()

    with File(vacio, "w") as h5:
        h5.create_dataset("lat", data=arange(0.0, 1.0, 0.1))
        h5.create_dataset("lon", data=arange(0.0, 1.0, 0.1))
        h5.create_dataset("precipitation", data=ones((10, 10), dtype=float32))

    assert (
        precipitacion_media(BytesIO(vacio.getvalue()), (-87.4, 12.8, -87.3, 12.9))
        is None
    )


########################################################################################


def test_asf_results_become_products(monkeypatch: MonkeyPatch) -> None:
    nombre = granulo(0, 33)

    resultado = SimpleNamespace(
        properties={
            "additionalUrls": [f"https://x/{nombre}.h5"],
            "bytes": {f"{nombre}.h5": {"bytes": 123}},
            "processingDate": "2026-07-20T00:00:00Z",
            "s3Urls": [f"s3://c/{nombre}_QA_STATS.h5", f"s3://c/{nombre}.h5"],
            "url": f"https://x/{nombre}.zip",
        },
    )

    producto = adquisiciones.desde_asf(resultado, Madurez.PROVISIONAL)

    assert producto is not None
    assert producto.https_url.endswith(".h5")
    assert producto.s3_url == f"s3://c/{nombre}.h5"
    assert producto.bytes == 123
    assert producto.procesado_at is not None
    assert (
        adquisiciones.desde_asf(
            SimpleNamespace(properties={"url": "https://x/otro.zip"}), Madurez.BETA
        )
        is None
    )

    monkeypatch.setattr(adquisiciones, "search", lambda **_: [resultado])

    region = SimpleNamespace(aoi_wkt=AOI)

    encontrados = adquisiciones.buscar_productos(
        region,  # ty: ignore[invalid-argument-type]
        date(2026, 7, 1),
        date(2026, 7, 2),
    )

    assert {p.madurez for p in encontrados} == set(Madurez)


def test_remote_opener_prefers_s3_inside_aws(monkeypatch: MonkeyPatch) -> None:
    abiertos: list[str] = []

    monkeypatch.setattr(adquisiciones, "sesion_earthdata", object)
    monkeypatch.setattr(
        adquisiciones,
        "ArchivoS3",
        lambda url, credenciales, hilos: abiertos.append(url),
    )
    monkeypatch.setattr(
        adquisiciones, "ArchivoRemoto", lambda url, sesion, hilos: abiertos.append(url)
    )
    monkeypatch.setattr(adquisiciones, "CredencialesS3", lambda sesion: object())
    monkeypatch.setattr(adquisiciones, "usar_s3", lambda modo: True)

    abrir = adquisiciones.abridor()

    abrir(SimpleNamespace(s3_url="s3://c/a.h5", https_url="https://x/a.h5"))  # ty: ignore[invalid-argument-type]
    abrir(SimpleNamespace(s3_url="", https_url="https://x/b.h5"))  # ty: ignore[invalid-argument-type]

    assert abiertos == ["s3://c/a.h5", "https://x/b.h5"]


def test_earthdata_session_uses_the_token(monkeypatch: MonkeyPatch) -> None:

    llamadas: list[str] = []

    monkeypatch.setattr(
        adquisiciones.MANGROOVE_CONFIG, "EARTHDATA_TOKEN", SecretStr("Bearer abc")
    )
    monkeypatch.setattr(
        adquisiciones.ASFSession,
        "auth_with_token",
        lambda self, token: llamadas.append(token),
    )

    adquisiciones.sesion_earthdata()

    assert llamadas == ["abc"]


def test_products_outside_the_region_are_discarded(
    region: Region, tmp_path: Path
) -> None:

    meta = granulo(0, 33)

    producto = Producto.objects.create(
        granulo=meta,
        coleccion="NISAR_L2_GCOV_PROVISIONAL_V1",
        madurez=Madurez.PROVISIONAL,
        crid="P05023",
        ciclo=20,
        track=33,
        frame=82,
        orbita="asc",
        inicio_at=datetime(2026, 6, 20, tzinfo=UTC),
        fin_at=datetime(2026, 6, 20, 0, 1, tzinfo=UTC),
        polarizaciones="DHDH",
        https_url="https://x/a.h5",
    )

    recorte = Recorte.objects.create(producto=producto, region=region)

    lejos = escribir_gcov(tmp_path / "lejos.h5", x0=100_000.0)

    adquisiciones.recortar(region, recorte, lambda p: ArchivoFalso(lejos.read_bytes()))  # ty: ignore[invalid-argument-type]

    recorte.refresh_from_db()

    assert recorte.estado == "descartado"
    assert "no cubre" in recorte.motivo_descarte


########################################################################################


def test_media_uploads_are_idempotent_and_detect_conflicts(operador: ApiUser) -> None:
    primero = subir(
        contenido=b"a",
        mime="text/csv",
        ruta="x/a.csv",
        visibilidad=MediaVisibility.PUBLIC,
        usuario=operador,
    )
    segundo = subir(
        contenido=b"a",
        mime="text/csv",
        ruta="x/a.csv",
        visibilidad=MediaVisibility.PUBLIC,
        usuario=operador,
    )

    assert primero.id == segundo.id

    with raises(AlmacenamientoError):
        subir(
            contenido=b"b",
            mime="text/csv",
            ruta="x/a.csv",
            visibilidad=MediaVisibility.PUBLIC,
            usuario=operador,
        )

    assert dimensiones(b"x", "text/csv") == (None, None)


def test_storage_failures_are_reported(operador: ApiUser, bunny: object) -> None:
    bunny.routes["put"].respond(500)  # ty: ignore[unresolved-attribute]

    with raises(AlmacenamientoError):
        subir(
            contenido=b"c",
            mime="text/csv",
            ruta="x/c.csv",
            visibilidad=MediaVisibility.PUBLIC,
            usuario=operador,
        )


def test_command_helpers_resolve_or_fail(region: Region, operador: ApiUser) -> None:
    assert region_por_codigo("chica") == region
    assert usuario_por_identificador("operador@mangroove.earth") == operador
    assert fecha("2026-07-01") == date(2026, 7, 1)

    for llamada in (
        lambda: region_por_codigo("nada"),
        lambda: usuario_por_identificador("nadie"),
        lambda: corrida_por_id("01a1dea3-395d-73dc-87f1-562e927f2900"),
        lambda: fecha("ayer"),
    ):
        with raises(CommandError):
            llamada()


def test_commands_run_end_to_end(db: None, operador: ApiUser, tmp_path: Path) -> None:
    aoi = tmp_path / "aoi.wkt"
    aoi.write_text(AOI, encoding="utf-8")

    salida = StringIO()

    call_command(
        "crearregion",
        "--codigo=cmd",
        "--nombre=Comando",
        f"--aoi={aoi}",
        "--marea",
        "-87.4",
        "12.8",
        stdout=salida,
    )

    assert "Región cmd" in salida.getvalue()

    with raises(CommandError):
        call_command(
            "crearcorrida", "--region=cmd", "--madurez=provisional", stdout=StringIO()
        )

    call_command("trabajador", stdout=StringIO())
    call_command("purgarcorridas", "--silencioso", stdout=StringIO())

    malo = tmp_path / "malo.wkt"
    malo.write_text("LINESTRING(0 0, 1 1)", encoding="utf-8")

    with raises(CommandError):
        call_command(
            "crearregion",
            "--codigo=otra",
            "--nombre=Otra",
            f"--aoi={malo}",
            "--marea",
            "0",
            "0",
            stdout=StringIO(),
        )

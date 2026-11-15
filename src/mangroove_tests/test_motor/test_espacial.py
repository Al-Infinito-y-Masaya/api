from json import dumps
from pathlib import Path

from numpy import (
    arange,
    array,
    float32,
    full,
    isfinite,
    log10,
    nan,
    ones,
    uint8,
    zeros,
)
from pytest import approx, mark, raises
from rasterio import open as abrir_raster
from rasterio.transform import from_origin

from mangroove_motor.agregacion import (
    a_db,
    a_lineal,
    agregar,
    cobertura,
    muestras_validas,
)
from mangroove_motor.auxiliares import (
    barreras_desde_geojson,
    cobertura_raster,
    codigos_a_indices,
    estanques_desde_geojson,
    geometrias_geojson,
    mascara_humedal,
    mascara_manglar_raster,
    paises_desde_geojson,
    rasterizar_poligono,
    reproyectar_raster,
)
from mangroove_motor.grilla import (
    AoiInvalidaError,
    Grilla,
    grilla_desde_caja,
    parsear_aoi,
    zona_utm,
)

########################################################################################

WKT: str = "POLYGON((-87.40 12.80,-87.30 12.80,-87.30 12.90,-87.40 12.90,-87.40 12.80))"


def grilla_chica() -> Grilla:
    return Grilla(
        epsg=32616, x0=400_000.0, y0=1_450_000.0, celda_m=100.0, ancho=4, alto=3
    )


def poligono_lonlat(
    grilla: Grilla, columnas: tuple[int, int], filas: tuple[int, int]
) -> dict:
    oeste, norte = grilla.centro(filas[0], columnas[0])
    este, sur = grilla.centro(filas[1], columnas[1])

    margen: float = grilla.celda_m * 0.4

    xs = [oeste - margen, este + margen, este + margen, oeste - margen, oeste - margen]
    ys = [norte + margen, norte + margen, sur - margen, sur - margen, norte + margen]

    lon, lat = grilla.lonlat(array(xs), array(ys))

    return {
        "coordinates": [list(zip(lon.tolist(), lat.tolist(), strict=True))],
        "type": "Polygon",
    }


########################################################################################


@mark.parametrize(
    ("lon", "lat", "epsg"),
    [
        (-87.2, 12.9, 32616),
        (-87.2, -12.9, 32716),
        (179.9, 1.0, 32660),
        (-180.0, 1.0, 32601),
    ],
)
def test_utm_zone_follows_the_centroid(lon: float, lat: float, epsg: int) -> None:
    assert zona_utm(lon, lat) == epsg


def test_grid_from_box_aligns_to_the_cell_size() -> None:
    grilla = grilla_desde_caja((-87.40, 12.80, -87.30, 12.90), celda_m=100.0)

    assert grilla.epsg == 32616
    assert grilla.x0 % 100 == 0
    assert grilla.y0 % 100 == 0
    assert grilla.n == grilla.ancho * grilla.alto
    assert grilla.hectareas_por_celda == approx(1.0)


def test_cell_codes_round_trip() -> None:
    grilla = grilla_chica()

    codigo = grilla.codigo(2, 3)

    assert codigo == "c_400350_1449750"
    assert grilla.celda_de_codigo(codigo) == (2, 3)


@mark.parametrize(
    "codigo", ["x_1_2", "c_1", "c_a_b", "c_399950_1449750", "c_400351_1449750"]
)
def test_invalid_or_foreign_codes_are_rejected(codigo: str) -> None:
    assert grilla_chica().celda_de_codigo(codigo) is None


def test_points_map_to_their_cell_and_outside_points_to_none() -> None:
    grilla = grilla_chica()

    lon, lat = grilla.lonlat(*grilla.centro(1, 2))

    assert grilla.celda_de_lonlat(float(lon), float(lat)) == (1, 2)

    lon, lat = grilla.lonlat(grilla.x0 - 50, grilla.y0 + 50)

    assert grilla.celda_de_lonlat(float(lon), float(lat)) is None


def test_border_points_fall_in_the_higher_cell() -> None:
    grilla = grilla_chica()

    filas, columnas = grilla.indice(grilla.x0 + 100.0, grilla.y0 - 100.0)

    assert (int(filas), int(columnas)) == (1, 1)


def test_aoi_parses_wkt_and_geojson_alike() -> None:
    desde_wkt = parsear_aoi(WKT)

    geojson = {
        "features": [{"geometry": desde_wkt.geojson}],
        "type": "FeatureCollection",
    }

    desde_geojson = parsear_aoi(dumps(geojson))

    assert (
        desde_wkt.caja == desde_geojson.caja == approx((-87.40, 12.80, -87.30, 12.90))
    )
    assert desde_wkt.centroide == approx((-87.35, 12.85))


def test_aoi_closes_open_rings_and_reads_multipolygons() -> None:
    abierto = {
        "coordinates": [[[[-87.4, 12.8], [-87.3, 12.8], [-87.3, 12.9], [-87.4, 12.9]]]],
        "type": "MultiPolygon",
    }

    aoi = parsear_aoi(dumps(abierto))

    assert aoi.anillo[0] == aoi.anillo[-1]


@mark.parametrize(
    "texto",
    [
        "LINESTRING(0 0, 1 1)",
        dumps({"coordinates": [0, 0], "type": "Point"}),
        "POLYGON((0 0, 1 0, 0 0))",
        "POLYGON((12.8 -97.4,12.9 -97.4,12.9 -97.3,12.8 -97.3,12.8 -97.4))",
    ],
)
def test_invalid_aoi_is_rejected(texto: str) -> None:
    with raises(AoiInvalidaError):
        parsear_aoi(texto)


########################################################################################


def test_aggregation_averages_linear_power() -> None:
    grilla = grilla_chica()

    xs = grilla.x0 + array([25.0, 75.0])
    ys = grilla.y0 - array([25.0, 75.0])

    bloque = array([[0.1, 0.01], [0.1, 0.01]])

    agregado = agregar(
        hh=bloque, hv=bloque, xs=xs, ys=ys, epsg=grilla.epsg, grilla=grilla
    )

    hh_db = agregado.en_db()[0]

    assert hh_db[0] == approx(10 * log10(0.055), abs=1e-5)
    assert hh_db[0] != approx((10 * log10(0.1) + 10 * log10(0.01)) / 2)
    assert not isfinite(hh_db[1:]).any()


def test_strict_mask_drops_partially_focused_samples() -> None:
    mascara = array([0, 1, 254, 255], dtype=uint8)

    assert muestras_validas(mascara, estricta=True).tolist() == [
        False,
        True,
        True,
        False,
    ]
    assert muestras_validas(mascara, estricta=False).tolist() == [
        True,
        True,
        True,
        False,
    ]


def test_two_frames_combine_by_sample_count() -> None:
    grilla = grilla_chica()

    xs = grilla.x0 + array([25.0])
    ys = grilla.y0 - array([25.0])

    uno = agregar(
        hh=array([[0.1]]),
        hv=array([[0.1]]),
        xs=xs,
        ys=ys,
        epsg=grilla.epsg,
        grilla=grilla,
    )
    dos = agregar(
        hh=array([[0.3, 0.3]]),
        hv=array([[0.3, 0.3]]),
        xs=grilla.x0 + array([25.0, 75.0]),
        ys=ys,
        epsg=grilla.epsg,
        grilla=grilla,
    )

    combinado = (uno + dos).en_db()

    assert a_lineal(combinado[0][0]) == approx((0.1 + 0.3 + 0.3) / 3, rel=1e-5)


def test_samples_in_another_projection_are_reprojected() -> None:
    grilla = grilla_chica()

    lon, lat = grilla.lonlat(*grilla.centro(0, 0))

    agregado = agregar(
        hh=array([[0.2]]),
        hv=array([[0.2]]),
        xs=lon.reshape(1),
        ys=lat.reshape(1),
        epsg=4326,
        grilla=grilla,
        mascara=array([[1]], dtype=uint8),
    )

    assert a_lineal(agregado.en_db()[0][0]) == approx(0.2, rel=1e-5)


def test_samples_outside_the_grid_or_invalid_are_ignored() -> None:
    grilla = grilla_chica()

    agregado = agregar(
        hh=array([[nan, -1.0, 0.5]]),
        hv=array([[nan, -1.0, 0.5]]),
        xs=array([grilla.x0 + 25, grilla.x0 + 125, grilla.x0 - 25]),
        ys=array([grilla.y0 - 25]),
        epsg=grilla.epsg,
        grilla=grilla,
    )

    assert int(agregado.hh.conteo.sum()) == 0


def test_coverage_counts_valid_cells_inside_the_area() -> None:
    db = full((2, 4), nan)
    db[:, :3] = -10.0

    assert cobertura(db, array([True, True, False, False])) == approx(1.0)
    assert cobertura(db, array([False, False, True, True])) == approx(0.5)
    assert cobertura(db, array([False] * 4)) == approx(0.0)


def test_db_conversion_round_trips() -> None:
    assert a_lineal(a_db(array([0.25]))) == approx([0.25])


########################################################################################


def test_polygons_rasterize_onto_the_grid() -> None:
    grilla = grilla_chica()

    mascara = rasterizar_poligono(poligono_lonlat(grilla, (1, 2), (0, 1)), grilla)

    assert mascara.reshape(3, 4)[:2, 1:3].all()
    assert mascara.sum() == 4


def test_barriers_distinguish_levees_from_roads() -> None:
    grilla = grilla_chica()

    geojson = {
        "features": [
            {
                "geometry": poligono_lonlat(grilla, (0, 0), (0, 2)),
                "properties": {"tipo": "borda"},
            },
            {
                "geometry": poligono_lonlat(grilla, (3, 3), (0, 2)),
                "properties": {"tipo": "Camino"},
            },
        ],
        "type": "FeatureCollection",
    }

    barreras = barreras_desde_geojson(geojson, grilla).reshape(3, 4)

    assert (barreras[:, 0] == 1).all()
    assert (barreras[:, 3] == 2).all()


def test_countries_and_ponds_get_indices() -> None:
    grilla = grilla_chica()

    paises = {
        "features": [
            {
                "geometry": poligono_lonlat(grilla, (0, 1), (0, 2)),
                "properties": {"iso": "ni"},
            },
            {
                "geometry": poligono_lonlat(grilla, (2, 3), (0, 2)),
                "properties": {"iso": "HN"},
            },
            {"geometry": poligono_lonlat(grilla, (2, 3), (0, 0)), "properties": {}},
        ],
        "type": "FeatureCollection",
    }

    indices, codigos = paises_desde_geojson(paises, grilla)

    assert codigos == ("NI", "HN")
    assert codigos_a_indices(codigos, indices)[:4] == ["NI", "NI", "HN", "HN"]

    estanques, poligonos = estanques_desde_geojson(
        {
            "geometry": poligono_lonlat(grilla, (1, 1), (1, 1)),
            "properties": {"id": "E-7"},
            "type": "Feature",
        },
        grilla,
    )

    assert [codigo for codigo, _ in poligonos] == ["E-7"]
    assert int(estanques.reshape(3, 4)[1, 1]) == 1


def test_bare_geometries_are_wrapped() -> None:
    assert len(geometrias_geojson({"coordinates": [], "type": "Polygon"})) == 1


def test_rasters_are_reprojected_to_the_grid(tmp_path: Path) -> None:
    grilla = grilla_chica()

    ruta = tmp_path / "fraccion.tif"

    with abrir_raster(
        ruta,
        "w",
        count=1,
        crs=grilla.crs,
        driver="GTiff",
        dtype="float32",
        height=6,
        transform=from_origin(grilla.x0, grilla.y0, 50.0, 50.0),
        width=8,
    ) as salida:
        valores = ones((6, 8), dtype=float32)
        valores[:, 4:] = 0.0
        salida.write(valores, 1)

    fraccion = reproyectar_raster(ruta, grilla)

    assert cobertura_raster(fraccion) == approx(1.0)
    assert mascara_manglar_raster(fraccion).reshape(3, 4)[:, :2].all()
    assert not mascara_manglar_raster(fraccion).reshape(3, 4)[:, 2:].any()


def test_wetland_excludes_slopes_heights_and_exclusions() -> None:
    grilla = grilla_chica()

    cotas = arange(12, dtype=float32)
    cotas[11] = 40.0

    exclusion = zeros(12, dtype=bool)
    exclusion[0] = True

    humedal = mascara_humedal(
        grilla,
        elevacion=cotas,
        exclusion=exclusion,
        pendiente_max=8.0,
        cota_max=15.0,
    )

    assert not humedal[0]
    assert not humedal[11]
    assert humedal[5]
    assert mascara_humedal(
        grilla,
        elevacion=None,
        exclusion=None,
        pendiente_max=8.0,
        cota_max=15.0,
    ).all()

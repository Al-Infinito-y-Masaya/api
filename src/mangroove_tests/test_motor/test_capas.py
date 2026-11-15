from io import BytesIO

from PIL import Image
from numpy import array, asarray, full, nan, zeros
from rasterio.io import MemoryFile

from mangroove_motor.analisis import Resultado
from mangroove_motor.capas import (
    AZULES,
    CODIGOS_CONEXION,
    SIN_DATO,
    Conexion,
    capa_clases,
    capa_continua,
    capa_desconexion,
    capa_rgb,
    codigos_conexion,
    geotiff,
    leyendas,
)
from mangroove_motor.sintetica import Escena
from mangroove_motor.types import Arreglo

########################################################################################


def decodificar(contenido: bytes) -> Arreglo:
    return asarray(Image.open(BytesIO(contenido)))


def test_rgb_layer_is_georeferenced_and_opaque_where_there_is_data(
    escena: Escena,
    resultado: Resultado,
) -> None:
    capa = capa_rgb(resultado.calibrado.hh[0], resultado.calibrado.hv[0], escena.grilla)

    imagen = decodificar(capa.contenido)

    oeste, sur, este, norte = capa.limites

    assert imagen.shape[2] == 4
    assert (imagen[..., 3] == 255).mean() > 0.95
    assert oeste < este
    assert sur < norte
    assert len(capa.sha256) == 64


def test_layers_are_byte_identical_between_runs(
    escena: Escena, resultado: Resultado
) -> None:
    primera = capa_clases(resultado.clasificacion.clases[3], escena.grilla)
    segunda = capa_clases(resultado.clasificacion.clases[3], escena.grilla)

    assert primera.sha256 == segunda.sha256


def test_connectivity_codes_and_layer(escena: Escena, resultado: Resultado) -> None:
    codigos = codigos_conexion(
        array([True, True, True, False]),
        array([True, True, False, False]),
        array([True, False, False, True]),
    )

    assert codigos.tolist() == [
        CODIGOS_CONEXION[Conexion.DESCONECTADA],
        CODIGOS_CONEXION[Conexion.CONECTADA],
        CODIGOS_CONEXION[Conexion.INSUFICIENTE],
        SIN_DATO,
    ]

    capa = capa_desconexion(
        codigos_conexion(
            resultado.en_mascara,
            resultado.frecuencias.datos_suficientes,
            resultado.desconectada,
        ),
        escena.grilla,
    )

    assert decodificar(capa.contenido)[..., 3].max() == 255


def test_continuous_layer_hatches_insufficient_cells(escena: Escena) -> None:
    valores = full(escena.grilla.n, 0.5)
    valores[:10] = nan

    tramada = zeros(escena.grilla.n, dtype=bool)
    tramada[:10] = True

    capa = capa_continua(valores, escena.grilla, colores=AZULES[::-1], tramada=tramada)

    assert (decodificar(capa.contenido)[..., 3] == 255).mean() > 0.95


def test_geotiff_keeps_values_and_projection(
    escena: Escena, resultado: Resultado
) -> None:
    contenido = geotiff(resultado.frecuencias.if_total, escena.grilla)

    with MemoryFile(contenido) as memoria, memoria.open() as raster:
        assert raster.crs.to_epsg() == escena.grilla.epsg
        assert raster.width == escena.grilla.ancho
        assert raster.read(1).reshape(-1)[0] == resultado.frecuencias.if_total[0]

    entero = geotiff(resultado.clasificacion.tipica, escena.grilla, entero=True)

    with MemoryFile(entero) as memoria, memoria.open() as raster:
        assert raster.dtypes[0] == "uint8"

    assert geotiff(resultado.frecuencias.if_total, escena.grilla) == contenido


def test_legends_name_every_layer() -> None:
    assert set(leyendas()) == {
        "clases",
        "desconexion",
        "if",
        "if_alta",
        "p_error",
        "cambio",
    }
    assert {c["codigo"] for c in leyendas()["clases"]} == {"NI", "IV", "OW", "NC"}

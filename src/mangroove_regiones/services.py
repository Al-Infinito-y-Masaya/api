from typing import TYPE_CHECKING

from django.db.transaction import atomic
from numpy import arange, empty, meshgrid

from mangroove_motor.auxiliares import rasterizar_poligono
from mangroove_motor.grilla import Aoi, Grilla, grilla_desde_caja, parsear_aoi
from mangroove_regiones.models import Celda, Region

if TYPE_CHECKING:
    from mangroove_motor.types import Arreglo

########################################################################################

LOTE_CELDAS: int = 10_000

########################################################################################


@atomic
def crear_region(  # ruff: ignore[too-many-arguments]
    *,
    codigo: str,
    nombre: str,
    aoi: str,
    marea: tuple[float, float],
    zona_horaria: str = "America/Managua",
    celda_m: int = 100,
    margen_m: int = 2000,
    zoom_inicial: int = 11,
) -> Region:
    poligono: Aoi = parsear_aoi(aoi)

    grilla: Grilla = grilla_desde_caja(poligono.caja, celda_m=float(celda_m))

    oeste, sur, este, norte = poligono.caja
    centro_lon, centro_lat = poligono.centroide

    region: Region = Region.objects.create(
        codigo=codigo,
        nombre=nombre,
        aoi_wkt=poligono.wkt,
        lon_min=oeste,
        lat_min=sur,
        lon_max=este,
        lat_max=norte,
        centro_lon=centro_lon,
        centro_lat=centro_lat,
        zoom_inicial=zoom_inicial,
        zona_horaria=zona_horaria,
        epsg=grilla.epsg,
        celda_m=celda_m,
        x0=grilla.x0,
        y0=grilla.y0,
        ancho=grilla.ancho,
        alto=grilla.alto,
        margen_m=margen_m,
        marea_lon=marea[0],
        marea_lat=marea[1],
    )

    crear_celdas(region, grilla)

    return region


def crear_celdas(region: Region, grilla: Grilla) -> None:
    columnas, filas = meshgrid(arange(grilla.ancho), arange(grilla.alto))

    filas_planas: Arreglo = filas.reshape(-1)
    columnas_planas: Arreglo = columnas.reshape(-1)

    lon, lat = grilla.lonlat(*grilla.centro(filas_planas, columnas_planas))

    for inicio in range(0, grilla.n, LOTE_CELDAS):
        fin: int = min(grilla.n, inicio + LOTE_CELDAS)

        Celda.objects.bulk_create(
            [
                Celda(
                    region=region,
                    fila=int(filas_planas[i]),
                    columna=int(columnas_planas[i]),
                    lon=round(float(lon[i]), 7),
                    lat=round(float(lat[i]), 7),
                )
                for i in range(inicio, fin)
            ],
        )


def dentro_aoi(region: Region) -> Arreglo:
    return rasterizar_poligono(parsear_aoi(region.aoi_wkt).geojson, region.grilla())  # ty: ignore[invalid-argument-type]


def ids_celdas(region: Region) -> Arreglo:
    grilla: Grilla = region.grilla()

    ids: Arreglo = empty(grilla.n, dtype=object)

    for celda_id, fila, columna in Celda.objects.filter(region=region).values_list(
        "id",
        "fila",
        "columna",
    ):
        ids[fila * grilla.ancho + columna] = celda_id

    return ids

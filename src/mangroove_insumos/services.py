from csv import DictReader
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from json import loads
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from django.db.transaction import atomic
from earthaccess import (
    login,
    open as abrir,
    search_data,
)
from h5py import File
from numpy import asarray, float32, isfinite
from rasterio.warp import Resampling, transform_geom
from shapely.geometry import shape

from api_media.enums import MediaVisibility
from mangroove_adquisiciones.models import Adquisicion
from mangroove_comun.archivos import (
    absoluta,
    guardar_arreglo,
    guardar_bytes,
    leer_arreglo,
    suma,
)
from mangroove_comun.config import MANGROOVE_CONFIG
from mangroove_comun.medios import subir
from mangroove_insumos.enums import FormatoInsumo, TipoInsumo, TipoSerie
from mangroove_insumos.models import (
    Estanque,
    EstimacionMarea,
    Insumo,
    LluviaDiaria,
    SerieCargada,
)
from mangroove_motor.auxiliares import (
    barreras_desde_geojson,
    cobertura_raster,
    estanques_desde_geojson,
    geometrias_geojson,
    mascara_manglar_raster,
    paises_desde_geojson,
    rasterizar_geometrias,
    reproyectar_raster,
)
from mangroove_motor.datos import Auxiliares
from mangroove_motor.marea import alturas_marea, interpolar_serie

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from api_auth.models import ApiUser
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo
    from mangroove_regiones.models import Region

########################################################################################

EXTENSIONES_RASTER: frozenset[str] = frozenset({".tif", ".tiff"})
EXTENSIONES_VECTOR: frozenset[str] = frozenset({".json", ".geojson"})

MIMES: dict[str, str] = {
    FormatoInsumo.RASTER: "image/tiff",
    FormatoInsumo.VECTOR: "application/geo+json",
}

COBERTURA_MINIMA: float = 0.5

DIAS_LLUVIA: int = 3

FUENTE_IMERG: dict[str, str] = {
    "late": "gpm_imerg_v07_late",
    "final": "gpm_imerg_v07_final",
}

PRODUCTO_IMERG: dict[str, str] = {
    "late": "GPM_3IMERGDL",
    "final": "GPM_3IMERGDF",
}

SIN_GRILLA: frozenset[str] = frozenset({TipoInsumo.AREAS_PROTEGIDAS})

########################################################################################


class InsumoInvalidoError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Procesado:
    grilla: Arreglo | None
    estanques: list[tuple[str, dict]]


########################################################################################


def formato_de(ruta: Path) -> FormatoInsumo:
    sufijo: str = ruta.suffix.lower()

    if sufijo in EXTENSIONES_RASTER:
        return FormatoInsumo.RASTER

    if sufijo in EXTENSIONES_VECTOR:
        return FormatoInsumo.VECTOR

    raise InsumoInvalidoError(f"Formato no admitido: {ruta.suffix}.")


def procesar(
    tipo: TipoInsumo, ruta: Path, formato: FormatoInsumo, grilla: Grilla
) -> Procesado:
    if formato == FormatoInsumo.RASTER:
        return Procesado(grilla=procesar_raster(tipo, ruta, grilla), estanques=[])

    objeto: dict = loads(ruta.read_text(encoding="utf-8"))

    if tipo == TipoInsumo.ESTANQUES:
        numeros, poligonos = estanques_desde_geojson(objeto, grilla)

        return Procesado(grilla=numeros, estanques=poligonos)

    if tipo == TipoInsumo.BARRERAS:
        return Procesado(grilla=barreras_desde_geojson(objeto, grilla), estanques=[])

    if tipo == TipoInsumo.PAISES:
        indices, _ = paises_desde_geojson(objeto, grilla)

        return Procesado(grilla=indices, estanques=[])

    if tipo in SIN_GRILLA:
        return Procesado(grilla=None, estanques=[])

    if tipo in {TipoInsumo.MANGLAR, TipoInsumo.EXCLUSION}:
        formas = [(g, 1) for g, _ in geometrias_geojson(objeto)]

        return Procesado(
            grilla=rasterizar_geometrias(formas, grilla, tocadas=False).astype(bool),
            estanques=[],
        )

    raise InsumoInvalidoError(f"El tipo {tipo} no se carga como vector.")


def procesar_raster(tipo: TipoInsumo, ruta: Path, grilla: Grilla) -> Arreglo:
    if tipo not in {
        TipoInsumo.MANGLAR,
        TipoInsumo.ELEVACION,
        TipoInsumo.OPTICO,
        TipoInsumo.BANDA_C,
    }:
        raise InsumoInvalidoError(f"El tipo {tipo} no se carga como ráster.")

    valores: Arreglo = reproyectar_raster(ruta, grilla, remuestreo=Resampling.average)

    if cobertura_raster(valores) < COBERTURA_MINIMA:
        raise InsumoInvalidoError(
            f"El archivo cubre solo el {cobertura_raster(valores):.0%} de la región.",
        )

    if tipo == TipoInsumo.MANGLAR:
        return mascara_manglar_raster(valores)

    return valores.astype(float32)


def area_hectareas(geometria: dict, grilla: Grilla) -> float:
    return (
        float(shape(transform_geom("EPSG:4326", grilla.crs, geometria)).area) / 10_000
    )


########################################################################################


@atomic
def cargar_insumo(  # ruff: ignore[too-many-arguments]
    *,
    region: Region,
    tipo: TipoInsumo,
    ruta: Path,
    fuente: str,
    licencia: str,
    usuario: ApiUser,
    fuente_url: str = "",
    fecha_dato: date | None = None,
    nubes_pct: float | None = None,
) -> Insumo:
    formato: FormatoInsumo = formato_de(ruta)

    contenido: bytes = ruta.read_bytes()
    huella: str = suma(contenido)

    existente: Insumo | None = Insumo.objects.filter(
        region=region, tipo=tipo, sha256=huella
    ).first()

    if existente is not None:
        return existente

    procesado: Procesado = procesar(tipo, ruta, formato, region.grilla())

    carpeta: Path = MANGROOVE_CONFIG.insumos / region.codigo / tipo / huella[:16]  # ty: ignore[unsupported-operator]

    guardar_bytes(carpeta / f"original{ruta.suffix.lower()}", contenido)

    grilla_guardada = (
        None
        if procesado.grilla is None
        else guardar_arreglo(carpeta / "grilla.npy", procesado.grilla)
    )

    media = subir(
        contenido=contenido,
        mime=MIMES[formato],
        ruta=f"insumos/{region.codigo}/{tipo}/{huella}{ruta.suffix.lower()}",
        usuario=usuario,
        visibilidad=MediaVisibility.PRIVATE,
    )

    insumo: Insumo = Insumo.objects.create(
        region=region,
        tipo=tipo,
        formato=formato,
        media=media,
        sha256=huella,
        grilla_archivo=grilla_guardada.relativa if grilla_guardada else "",
        grilla_sha256=grilla_guardada.sha256 if grilla_guardada else "",
        fuente=fuente,
        fuente_url=fuente_url,
        licencia=licencia,
        fecha_dato=fecha_dato,
        nubes_pct=nubes_pct,
        cargado_por=usuario,
    )

    if procesado.estanques:
        grilla: Grilla = region.grilla()

        Estanque.objects.bulk_create(
            [
                Estanque(
                    insumo=insumo,
                    numero=numero,
                    codigo=codigo[:30],
                    geometria=geometria,
                    area_ha=max(area_hectareas(geometria, grilla), 1e-6),
                )
                for numero, (codigo, geometria) in enumerate(procesado.estanques, 1)
            ],
        )

    return insumo


def vigentes(region: Region) -> dict[str, Insumo]:
    ultimos: dict[str, Insumo] = {}

    for insumo in Insumo.objects.filter(region=region).order_by("tipo", "version"):
        ultimos[insumo.tipo] = insumo

    return ultimos


def original_de(insumo: Insumo) -> Path:
    carpeta: Path = (
        absoluta(insumo.grilla_archivo).parent  # ty: ignore[invalid-argument-type]
        if insumo.grilla_archivo
        else (
            MANGROOVE_CONFIG.insumos
            / insumo.region.codigo  # ty: ignore[unresolved-attribute]
            / insumo.tipo
            / insumo.sha256[:16]  # ty: ignore[not-subscriptable]
        )
    )

    return next(carpeta.glob("original.*"))


def auxiliares_de(insumos: Iterable[Insumo], grilla: Grilla) -> Auxiliares:
    por_tipo: dict[str, Insumo] = {i.tipo: i for i in insumos}  # ty: ignore[invalid-assignment]

    def grilla_de(tipo: str) -> Arreglo | None:
        insumo: Insumo | None = por_tipo.get(tipo)

        if insumo is None or not insumo.grilla_archivo:
            return None

        return asarray(leer_arreglo(insumo.grilla_archivo))  # ty: ignore[invalid-argument-type]

    codigos: tuple[str, ...] = ()

    if TipoInsumo.PAISES in por_tipo:
        _, codigos = paises_desde_geojson(
            loads(original_de(por_tipo[TipoInsumo.PAISES]).read_text(encoding="utf-8")),
            grilla,
        )

    manglar: Arreglo | None = grilla_de(TipoInsumo.MANGLAR)

    return Auxiliares(
        manglar=Auxiliares.vacios(grilla).manglar
        if manglar is None
        else manglar.astype(bool),
        exclusion=grilla_de(TipoInsumo.EXCLUSION),
        elevacion=grilla_de(TipoInsumo.ELEVACION),
        barreras=grilla_de(TipoInsumo.BARRERAS),
        estanques=grilla_de(TipoInsumo.ESTANQUES),
        paises=grilla_de(TipoInsumo.PAISES),
        codigos_paises=codigos,
    )


########################################################################################


def leer_csv(contenido: str, columnas: Sequence[str]) -> list[dict[str, str]]:
    lector: DictReader = DictReader(StringIO(contenido))

    if lector.fieldnames is None or not set(columnas) <= set(lector.fieldnames):
        raise InsumoInvalidoError(
            f"El CSV debe tener las columnas {', '.join(columnas)}."
        )

    return list(lector)


def instante_utc(texto: str) -> datetime:
    valor: datetime = datetime.fromisoformat(texto.strip())

    return valor.replace(tzinfo=UTC) if valor.tzinfo is None else valor.astimezone(UTC)


@atomic
def cargar_serie(
    *,
    region: Region,
    tipo: TipoSerie,
    ruta: Path,
    fuente: str,
    usuario: ApiUser,
) -> SerieCargada:
    contenido: bytes = ruta.read_bytes()
    texto: str = contenido.decode("utf-8")

    if tipo == TipoSerie.MAREA:
        filas = leer_csv(texto, ("datetime", "tide_m"))
        puntos: list[tuple[datetime, float]] = [
            (instante_utc(f["datetime"]), float(f["tide_m"])) for f in filas
        ]
    else:
        filas = leer_csv(texto, ("date", "rain_mm"))
        dias: list[tuple[date, float]] = [
            (date.fromisoformat(f["date"].strip()[:10]), float(f["rain_mm"]))
            for f in filas
        ]

    media = subir(
        contenido=contenido,
        mime="text/csv",
        ruta=f"series/{region.codigo}/{tipo}/{suma(contenido)}.csv",
        usuario=usuario,
        visibilidad=MediaVisibility.PRIVATE,
    )

    serie: SerieCargada = SerieCargada.objects.create(
        region=region,
        tipo=tipo,
        media=media,
        sha256=suma(contenido),
        fuente=fuente,
        cargada_por=usuario,
    )

    if tipo == TipoSerie.MAREA:
        adquisiciones: list[Adquisicion] = list(
            Adquisicion.objects.filter(region=region)
        )

        alturas = interpolar_serie([a.inicio_at for a in adquisiciones], puntos)  # ty: ignore[invalid-argument-type]

        EstimacionMarea.objects.bulk_create(
            [
                EstimacionMarea(
                    adquisicion=a, modelo=f"serie:{serie.id}", serie=serie, altura_m=h
                )
                for a, h in zip(adquisiciones, alturas, strict=True)
                if h is not None
            ],
        )
    else:
        LluviaDiaria.objects.bulk_create(
            [
                LluviaDiaria(
                    region=region,
                    fecha=d,
                    fuente=f"serie:{serie.id}",
                    serie=serie,
                    mm=mm,
                )
                for d, mm in dias
            ],
        )

    return serie


########################################################################################


def estimar_mareas(region: Region, adquisiciones: Iterable[Adquisicion]) -> int:
    directorio: Path | None = MANGROOVE_CONFIG.MANGROOVE_MAREA
    modelo: str = MANGROOVE_CONFIG.MANGROOVE_MODELO_MAREA

    if directorio is None:
        return 0

    pendientes: list[Adquisicion] = [
        a
        for a in adquisiciones
        if not a.mareas.filter(modelo=modelo).exists()  # ty: ignore[unresolved-attribute]
    ]

    alturas = alturas_marea(
        [a.inicio_at for a in pendientes],  # ty: ignore[invalid-argument-type]
        lon=region.marea_lon,  # ty: ignore[invalid-argument-type]
        lat=region.marea_lat,  # ty: ignore[invalid-argument-type]
        directorio=directorio,
        modelo=modelo,
    )

    creadas: list[EstimacionMarea] = EstimacionMarea.objects.bulk_create(
        [
            EstimacionMarea(adquisicion=a, modelo=modelo, altura_m=h)
            for a, h in zip(pendientes, alturas, strict=True)
            if h is not None
        ],
    )

    return len(creadas)


def lluvia_3d(region: Region, instante: datetime, fuente: str) -> float | None:
    if not fuente:
        return None

    local: date = instante.astimezone(ZoneInfo(region.zona_horaria)).date()  # ty: ignore[invalid-argument-type]

    dias: list[date] = [local - timedelta(days=k) for k in range(DIAS_LLUVIA)]

    valores: dict[date, float] = dict(
        LluviaDiaria.objects.filter(
            region=region, fuente=fuente, fecha__in=dias
        ).values_list(
            "fecha",
            "mm",
        ),
    )

    if len(valores) < DIAS_LLUVIA:
        return None

    return round(sum(valores.values()), 1)


########################################################################################


def precipitacion_media(
    archivo: object, caja: tuple[float, float, float, float]
) -> float | None:
    oeste, sur, este, norte = caja

    with File(archivo, "r") as h5:
        grupo = h5.get("Grid", h5)

        lat: Arreglo = asarray(grupo["lat"][()])
        lon: Arreglo = asarray(grupo["lon"][()])
        precipitacion: Arreglo = asarray(grupo["precipitation"][()], dtype=float32)

    if precipitacion.ndim == 3:  # ruff: ignore[magic-value-comparison]
        precipitacion = precipitacion[0]

    dentro_lon = (lon >= oeste - 0.05) & (lon <= este + 0.05)
    dentro_lat = (lat >= sur - 0.05) & (lat <= norte + 0.05)

    recorte: Arreglo = precipitacion[dentro_lon][:, dentro_lat]

    recorte = recorte[isfinite(recorte) & (recorte >= 0)]

    if recorte.size == 0:
        return None

    return round(float(recorte.mean()), 2)


def obtener_lluvia(
    region: Region,
    *,
    desde: date,
    hasta: date,
    corrida_imerg: str = "late",
) -> int:
    fuente: str = FUENTE_IMERG[corrida_imerg]

    login(strategy="environment")

    resultados: list = search_data(
        bounding_box=(region.lon_min, region.lat_min, region.lon_max, region.lat_max),
        short_name=PRODUCTO_IMERG[corrida_imerg],
        temporal=(desde.isoformat(), hasta.isoformat()),
        version="07",
    )

    archivos: list = abrir(resultados)

    creadas: int = 0

    caja: tuple[float, float, float, float] = (  # ty: ignore[invalid-assignment]
        region.lon_min,
        region.lat_min,
        region.lon_max,
        region.lat_max,
    )

    for resultado, archivo in zip(resultados, archivos, strict=True):
        dia: date = date.fromisoformat(
            str(
                resultado["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
            )[:10],
        )

        mm: float | None = precipitacion_media(archivo, caja)

        if mm is None:
            continue

        _, nueva = LluviaDiaria.objects.get_or_create(
            region=region,
            fecha=dia,
            fuente=fuente,
            defaults={"mm": mm},
        )

        creadas += int(nueva)

    return creadas

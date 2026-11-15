from csv import writer
from dataclasses import asdict
from enum import StrEnum
from io import StringIO
from typing import TYPE_CHECKING

from django.utils.timezone import now

from mangroove_adquisiciones.models import Adquisicion, AdquisicionRecorte, Brecha
from mangroove_analisis.models import (
    Corrida,
    CorridaFecha,
    PruebaHipotesis,
    ResultadoCelda,
    ResultadoEstanque,
    ResumenFecha,
    ResumenPais,
)
from mangroove_motor.capas import leyendas
from mangroove_motor.perfil import Clase
from mangroove_publicacion.enums import POR_FECHA, TipoArtefacto

if TYPE_CHECKING:
    from mangroove_publicacion.models import Artefacto
    from mangroove_regiones.models import Celda

########################################################################################

FORMATO: str = "mangroove/1"

SIN_DATO_DB: int = -32768

ESCALA_DB: int = 100

CAPAS_CORRIDA: tuple[str, ...] = (
    TipoArtefacto.IF_ALTA,
    TipoArtefacto.IF,
    TipoArtefacto.DESCONEXION,
    TipoArtefacto.P_ERROR,
    TipoArtefacto.CAMBIO,
)

EXTENSIONES: dict[str, str] = {
    "csv": "csv",
    "geojson": "geojson",
    "json": "json",
    "png": "png",
    "tif": "tif",
}


class Base(StrEnum):
    API = "api"
    ESTATICO = "estatico"


########################################################################################


def prefijo(corrida: Corrida) -> str:
    return f"regiones/{corrida.region.codigo}/versiones/{corrida.version}"  # ty: ignore[unresolved-attribute]


def ruta_estatica(corrida: Corrida, tipo: str, formato: str, fecha: str = "") -> str:
    sufijo: str = f"/{fecha}" if fecha else ""

    base: str = f"{corrida.region.codigo}/{corrida.version}"  # ty: ignore[unresolved-attribute]

    return f"{base}/{tipo}{sufijo}.{EXTENSIONES[formato]}"


def ruta_capa(corrida: Corrida, tipo: str, base: Base, fecha: str = "") -> str:
    if base == Base.ESTATICO:
        return ruta_estatica(corrida, tipo, "png", fecha)

    if fecha:
        return f"{prefijo(corrida)}/fechas/{fecha}/capas/{tipo}/"

    return f"{prefijo(corrida)}/capas/{tipo}/"


def instante(valor: object) -> str:
    return valor.isoformat().replace("+00:00", "Z")  # ty: ignore[unresolved-attribute]


########################################################################################


def manifiesto(corrida: Corrida, base: Base) -> dict:
    region = corrida.region

    fechas: list[CorridaFecha] = list(
        corrida.fechas.select_related("adquisicion").order_by("orden"),  # ty: ignore[unresolved-attribute]
    )

    adquisiciones: list[Adquisicion] = [f.adquisicion for f in fechas]  # ty: ignore[invalid-assignment]

    limites: Artefacto | None = corrida.artefactos.filter(formato="png").first()  # ty: ignore[unresolved-attribute]

    perfil = corrida.perfil

    umbrales: dict = {"perfil": perfil.codigo, "version": perfil.version} | {  # ty: ignore[unresolved-attribute]
        k: (v.value if isinstance(v, StrEnum) else v)
        for k, v in asdict(perfil.a_perfil()).items()  # ty: ignore[unresolved-attribute]
    }

    tiene_estanques: bool = corrida.estanques.exists()  # ty: ignore[unresolved-attribute]

    capas: dict[str, str] = {
        tipo: ruta_capa(corrida, tipo, base) for tipo in CAPAS_CORRIDA
    }

    if tiene_estanques:
        capas["estanques"] = (
            ruta_estatica(corrida, TipoArtefacto.ESTANQUES, "geojson")
            if base == Base.ESTATICO
            else f"{prefijo(corrida)}/estanques/"
        )

    tiene_relato: bool = corrida.artefactos.filter(tipo=TipoArtefacto.RELATO).exists()  # ty: ignore[unresolved-attribute]

    inicio = adquisiciones[0].inicio_at if adquisiciones else None
    fin = adquisiciones[-1].inicio_at if adquisiciones else None

    brechas: list[dict] = [
        {
            "desde": instante(b.rango.lower),
            "hasta": instante(b.rango.upper),
            "motivo": b.motivo,
        }
        for b in Brecha.objects.order_by("rango")
        if inicio is not None and b.rango.upper >= inicio and b.rango.lower <= fin
    ]

    return {
        "formato": FORMATO,
        "version": corrida.version,
        "generado": instante(corrida.terminada_at or now()),
        "region": {
            "codigo": region.codigo,  # ty: ignore[unresolved-attribute]
            "nombre": region.nombre,  # ty: ignore[unresolved-attribute]
            "bbox": [region.lon_min, region.lat_min, region.lon_max, region.lat_max],  # ty: ignore[unresolved-attribute]
            "centro": [region.centro_lon, region.centro_lat],  # ty: ignore[unresolved-attribute]
            "zoom_inicial": region.zoom_inicial,  # ty: ignore[unresolved-attribute]
            "zona_horaria": region.zona_horaria,  # ty: ignore[unresolved-attribute]
            "grilla": {
                "epsg": region.epsg,  # ty: ignore[unresolved-attribute]
                "celda_m": region.celda_m,  # ty: ignore[unresolved-attribute]
                "x0": region.x0,  # ty: ignore[unresolved-attribute]
                "y0": region.y0,  # ty: ignore[unresolved-attribute]
                "ancho": region.ancho,  # ty: ignore[unresolved-attribute]
                "alto": region.alto,  # ty: ignore[unresolved-attribute]
            },
        },
        "fuente": {
            "mision": "NISAR",
            "producto": "L2 GCOV",
            "madurez": corrida.madurez,
            "crids": sorted({a.crid for a in adquisiciones}),
        },
        "fechas": [
            {
                "id": f.fecha_codigo,
                "fecha_hora": instante(f.adquisicion.inicio_at),  # ty: ignore[unresolved-attribute]
                "track": f.adquisicion.track,  # ty: ignore[unresolved-attribute]
                "orbita": f.adquisicion.orbita,  # ty: ignore[unresolved-attribute]
                "crid": f.adquisicion.crid,  # ty: ignore[unresolved-attribute]
                "incidencia": f.adquisicion.incidencia,  # ty: ignore[unresolved-attribute]
                "cobertura": f.adquisicion.cobertura,  # ty: ignore[unresolved-attribute]
                "marea_m": f.marea_m,
                "marea_nivel": f.marea_nivel,
                "lluvia_3d_mm": f.lluvia_3d_mm,
                "usada_en_if_alta": f.usada_en_if_alta,
                "capas": {
                    tipo: ruta_capa(corrida, tipo, base, f.fecha_codigo)  # ty: ignore[invalid-argument-type]
                    for tipo in POR_FECHA
                },
            }
            for f in fechas
        ],
        "brechas": brechas,
        "limites": (
            [limites.oeste, limites.sur, limites.este, limites.norte]
            if limites
            else None
        ),
        "capas": capas,
        "relato": (
            (
                ruta_estatica(corrida, TipoArtefacto.RELATO, "json")
                if base == Base.ESTATICO
                else f"{prefijo(corrida)}/relato/"
            )
            if tiene_relato
            else None
        ),
        "umbrales": umbrales,
        "leyendas": leyendas(),
        "codigo": corrida.codigo_version,
        "exploracion": False,
    }


########################################################################################


def celda(resultado: ResultadoCelda, corrida: Corrida, celda_modelo: Celda) -> dict:
    fechas: list[str] = list(
        corrida.fechas.order_by("orden").values_list("fecha_codigo", flat=True)  # ty: ignore[unresolved-attribute]
    )

    def db(valor: int) -> float | None:
        return None if valor == SIN_DATO_DB else valor / ESCALA_DB

    metricas: dict | None = None

    if resultado.en_mascara:
        metricas = {
            "if": resultado.if_total,
            "if_alta": resultado.if_alta,
            "n_fechas": resultado.n_fechas,
            "n_fechas_alta": resultado.n_fechas_alta,
            "desconectada": resultado.desconectada,
            "datos_suficientes": resultado.datos_suficientes,
            "p_error": resultado.p_error,
            "if_esperada": resultado.if_esperada,
        }

    cambio: dict | None = None

    if resultado.cambio_orden is not None:
        cambio = {
            "fecha_id": fechas[resultado.cambio_orden],  # ty: ignore[invalid-argument-type]
            "confianza": resultado.cambio_confianza,
            "delta_hv_db": resultado.cambio_delta_hv_db,
        }

    coherencia: list[int] = list(resultado.coherencia or [])  # ty: ignore[invalid-argument-type]

    return {
        "id": celda_modelo.codigo,
        "centroide": [celda_modelo.lon, celda_modelo.lat],
        "pais": resultado.pais,
        "en_mascara": resultado.en_mascara,
        "metricas": metricas,
        "cambio": cambio,
        "serie": [
            {
                "fecha_id": fecha,
                "hh_db": db(resultado.hh[k]),  # ty: ignore[not-subscriptable]
                "hv_db": db(resultado.hv[k]),  # ty: ignore[not-subscriptable]
                "coherencia": coherencia[k] / 1000 if coherencia else None,
                "clase": Clase(resultado.clases[k]).name,  # ty: ignore[not-subscriptable]
            }
            for k, fecha in enumerate(fechas)
        ],
    }


########################################################################################


def resumen(corrida: Corrida) -> dict:
    return {
        "version": corrida.version,
        "paises": [
            {
                "pais": r.pais,
                "n_celdas": r.n_celdas,
                "ha_manglar": r.ha_manglar,
                "ha_desconectada": r.ha_desconectada,
                "ha_insuficiente": r.ha_insuficiente,
                "ha_perdida_copa": r.ha_perdida_copa,
                "ha_iv_tipica": r.ha_iv_tipica,
                "ha_ow_tipica": r.ha_ow_tipica,
                "ha_ni_tipica": r.ha_ni_tipica,
            }
            for r in ResumenPais.objects.filter(corrida=corrida).order_by("pais")
        ],
        "fechas": [
            {
                "fecha_id": r.corrida_fecha.fecha_codigo,
                "pais": r.pais,
                "ha_iv": r.ha_iv,
                "ha_ow": r.ha_ow,
                "ha_ni": r.ha_ni,
                "ha_nc": r.ha_nc,
                "ha_nd": r.ha_nd,
            }
            for r in ResumenFecha.objects
            .filter(corrida=corrida)
            .select_related("corrida_fecha")
            .order_by("corrida_fecha__orden", "pais")
        ],
    }


def resumen_csv(corrida: Corrida) -> str:
    datos: dict = resumen(corrida)

    salida: StringIO = StringIO()
    escritor = writer(salida, lineterminator="\n")

    escritor.writerow(["ambito", "fecha_id", "pais", "indicador", "hectareas"])

    for fila in datos["paises"]:
        for indicador in (
            "ha_manglar",
            "ha_desconectada",
            "ha_insuficiente",
            "ha_perdida_copa",
            "ha_iv_tipica",
            "ha_ow_tipica",
            "ha_ni_tipica",
        ):
            escritor.writerow([
                "region",
                "",
                fila["pais"],
                indicador,
                round(fila[indicador], 4),
            ])

    for fila in datos["fechas"]:
        for indicador in ("ha_iv", "ha_ow", "ha_ni", "ha_nc", "ha_nd"):
            escritor.writerow(
                [
                    "fecha",
                    fila["fecha_id"],
                    fila["pais"],
                    indicador,
                    round(fila[indicador], 4),
                ],
            )

    return salida.getvalue()


def hipotesis(corrida: Corrida) -> list[dict]:
    return [
        {
            "codigo": h.codigo,
            "prueba": h.prueba,
            "grupo_a": h.grupo_a,
            "grupo_b": h.grupo_b,
            "evaluable": h.evaluable,
            "motivo": h.motivo,
            "n_a": h.n_a,
            "n_b": h.n_b,
            "mediana_a": h.mediana_a,
            "mediana_b": h.mediana_b,
            "estadistico": h.estadistico,
            "z": h.z,
            "p_valor": h.p_valor,
            "efecto": h.efecto,
        }
        for h in PruebaHipotesis.objects.filter(corrida=corrida).order_by("codigo")
    ]


def estanques(corrida: Corrida) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": r.estanque.geometria,
                "properties": {
                    "codigo": r.estanque.codigo,
                    "area_ha": r.area_ha,
                    "cv": r.cv,
                    "activo": r.activo,
                    "dist_canal_km": r.dist_canal_km,
                    "if_vecino": r.if_vecino,
                    "puntaje": r.puntaje,
                },
            }
            for r in ResultadoEstanque.objects
            .filter(corrida=corrida)
            .select_related("estanque")
            .order_by("estanque__numero")
        ],
    }


def metodo(corrida: Corrida) -> dict:
    return {
        "version": corrida.version,
        "codigo": corrida.codigo_version,
        "madurez": corrida.madurez,
        "modelo_marea": corrida.modelo_marea,
        "fuente_lluvia": corrida.fuente_lluvia,
        "semilla": corrida.semilla,
        "perfil": {"codigo": corrida.perfil.codigo, "version": corrida.perfil.version},  # ty: ignore[unresolved-attribute]
        "productos": [
            {
                "fecha_id": f.fecha_codigo,
                "granulos": sorted(
                    AdquisicionRecorte.objects.filter(
                        adquisicion_id=f.adquisicion_id
                    ).values_list(
                        "recorte__producto__granulo",
                        flat=True,
                    ),
                ),
                "crid": f.adquisicion.crid,
            }
            for f in corrida.fechas.select_related("adquisicion").order_by("orden")  # ty: ignore[unresolved-attribute]
        ],
        "insumos": [
            {
                "tipo": ci.insumo.tipo,
                "version": ci.insumo.version,
                "fuente": ci.insumo.fuente,
                "fuente_url": ci.insumo.fuente_url,
                "licencia": ci.insumo.licencia,
                "sha256": ci.insumo.sha256,
            }
            for ci in corrida.insumos.select_related("insumo").order_by("tipo")  # ty: ignore[unresolved-attribute]
        ],
        "creditos": [
            "NASA/JPL-Caltech e ISRO: misión NISAR.",
            "Alaska Satellite Facility DAAC: distribución de productos NISAR.",
        ],
        "licencia_datos": "CC-BY-4.0",
    }

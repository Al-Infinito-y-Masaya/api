from dataclasses import dataclass
from json import dumps
from logging import getLogger
from typing import TYPE_CHECKING

from django.db.transaction import atomic
from django.utils.timezone import now
from numpy import asarray, float64, full, int16, nan, uint8, where

from api_media.enums import MediaVisibility
from mangroove_analisis.enums import EstadoCorrida
from mangroove_analisis.models import (
    Corrida,
    CorridaFecha,
    CorridaInsumo,
    PruebaHipotesis,
    ResultadoCelda,
    ResultadoEstanque,
    ResumenFecha,
    ResumenPais,
)
from mangroove_analisis.services import CorridaInvalidaError, retirar_corrida
from mangroove_comun.archivos import absoluta, suma
from mangroove_comun.medios import borrar, escribir_publico, subir
from mangroove_motor.capas import (
    AZULES,
    NARANJAS,
    RANGO_CAMBIO,
    Capa,
    capa_clases,
    capa_continua,
    capa_desconexion,
    capa_rgb,
    codigos_conexion,
    geotiff,
)
from mangroove_publicacion.contrato import (
    Base,
    estanques,
    manifiesto,
    metodo,
    resumen,
    resumen_csv,
    ruta_estatica,
)
from mangroove_publicacion.enums import FormatoArtefacto, TipoArtefacto
from mangroove_publicacion.models import Artefacto
from mangroove_publicacion.relato import relato

if TYPE_CHECKING:
    from api_auth.models import ApiUser
    from api_media.models import ApiMedia
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo

########################################################################################

LOG = getLogger(__name__)

MIMES: dict[str, str] = {
    FormatoArtefacto.CSV: "text/csv",
    FormatoArtefacto.GEOJSON: "application/geo+json",
    FormatoArtefacto.JSON: "application/json",
    FormatoArtefacto.PNG: "image/png",
    FormatoArtefacto.TIF: "image/tiff",
}

SIN_DATO_DB: int = -32768

########################################################################################


@dataclass(frozen=True, slots=True)
class Matrices:
    hh: Arreglo
    hv: Arreglo
    clases: Arreglo
    tipica: Arreglo
    en_mascara: Arreglo
    suficientes: Arreglo
    desconectada: Arreglo
    if_total: Arreglo
    if_alta: Arreglo
    p_error: Arreglo
    delta: Arreglo


def matrices(  # ruff: ignore[too-many-locals]
    corrida: Corrida,
    grilla: Grilla,
) -> Matrices:
    n: int = grilla.n
    t: int = corrida.n_fechas  # ty: ignore[invalid-assignment]

    hh: Arreglo = full((t, n), nan)
    hv: Arreglo = full((t, n), nan)
    clases: Arreglo = full((t, n), 4, dtype=uint8)
    tipica: Arreglo = full(n, 4, dtype=uint8)
    en_mascara: Arreglo = full(n, fill_value=False)
    suficientes: Arreglo = full(n, fill_value=False)
    desconectada: Arreglo = full(n, fill_value=False)
    if_total: Arreglo = full(n, nan)
    if_alta: Arreglo = full(n, nan)
    p_error: Arreglo = full(n, nan)
    delta: Arreglo = full(n, nan)

    filas = ResultadoCelda.objects.filter(corrida=corrida).values_list(
        "celda__fila",
        "celda__columna",
        "hh",
        "hv",
        "clases",
        "clase_tipica",
        "en_mascara",
        "datos_suficientes",
        "desconectada",
        "if_total",
        "if_alta",
        "p_error",
        "cambio_delta_hv_db",
    )

    for fila in filas.iterator(chunk_size=5000):
        i: int = fila[0] * grilla.ancho + fila[1]

        valores_hh: Arreglo = asarray(fila[2], dtype=int16)
        valores_hv: Arreglo = asarray(fila[3], dtype=int16)

        hh[:, i] = where(valores_hh == SIN_DATO_DB, nan, valores_hh / 100)
        hv[:, i] = where(valores_hv == SIN_DATO_DB, nan, valores_hv / 100)
        clases[:, i] = fila[4]
        tipica[i] = fila[5]
        en_mascara[i] = fila[6]
        suficientes[i] = fila[7]
        desconectada[i] = fila[8]
        if_total[i] = nan if fila[9] is None else fila[9]
        if_alta[i] = nan if fila[10] is None else fila[10]
        p_error[i] = nan if fila[11] is None else fila[11]
        delta[i] = nan if fila[12] is None else fila[12]

    return Matrices(
        hh=hh,
        hv=hv,
        clases=clases,
        tipica=tipica,
        en_mascara=en_mascara,
        suficientes=suficientes,
        desconectada=desconectada,
        if_total=if_total,
        if_alta=if_alta,
        p_error=p_error,
        delta=delta,
    )


########################################################################################


def registrar(  # ruff: ignore[too-many-arguments]
    corrida: Corrida,
    *,
    tipo: str,
    formato: str,
    contenido: bytes,
    usuario: ApiUser,
    fecha: CorridaFecha | None = None,
    limites: tuple[float, float, float, float] | None = None,
) -> Artefacto:
    media: ApiMedia = subir(
        contenido=contenido,
        mime=MIMES[formato],
        ruta=ruta_estatica(corrida, tipo, formato, fecha.fecha_codigo if fecha else ""),  # ty: ignore[invalid-argument-type]
        usuario=usuario,
        visibilidad=MediaVisibility.PUBLIC,
    )

    oeste, sur, este, norte = limites or (None, None, None, None)

    return Artefacto.objects.create(
        corrida=corrida,
        corrida_fecha=fecha,
        tipo=tipo,
        formato=formato,
        media=media,
        sha256=suma(contenido),
        bytes=len(contenido),
        oeste=oeste,
        sur=sur,
        este=este,
        norte=norte,
    )


def registrar_capa(
    corrida: Corrida,
    tipo: str,
    capa: Capa,
    usuario: ApiUser,
    fecha: CorridaFecha | None = None,
) -> Artefacto:
    return registrar(
        corrida,
        tipo=tipo,
        formato=FormatoArtefacto.PNG,
        contenido=capa.contenido,
        usuario=usuario,
        fecha=fecha,
        limites=capa.limites,
    )


def json_bytes(objeto: object) -> bytes:
    return dumps(
        objeto, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def escribir_vigente(corrida: Corrida) -> None:
    contenido: bytes = json_bytes(
        {"region": corrida.region.codigo, "version": corrida.version},  # ty: ignore[unresolved-attribute]
    )

    escribir_publico(f"{corrida.region.codigo}/vigente.json", contenido)  # ty: ignore[unresolved-attribute]


########################################################################################


def generar_artefactos(corrida: Corrida, usuario: ApiUser) -> None:
    grilla: Grilla = corrida.region.grilla()  # ty: ignore[unresolved-attribute]

    m: Matrices = matrices(corrida, grilla)

    for fecha in corrida.fechas.order_by("orden"):  # ty: ignore[unresolved-attribute]
        k: int = fecha.orden

        registrar_capa(
            corrida,
            TipoArtefacto.RGB,
            capa_rgb(m.hh[k], m.hv[k], grilla),
            usuario,
            fecha,
        )

        registrar_capa(
            corrida,
            TipoArtefacto.CLASES,
            capa_clases(m.clases[k], grilla),
            usuario,
            fecha,
        )

    insuficientes: Arreglo = m.en_mascara & ~m.suficientes

    capas: dict[str, Capa] = {
        TipoArtefacto.IF_ALTA: capa_continua(
            m.if_alta, grilla, colores=AZULES[::-1], tramada=insuficientes
        ),
        TipoArtefacto.IF: capa_continua(m.if_total, grilla, colores=AZULES[::-1]),
        TipoArtefacto.DESCONEXION: capa_desconexion(
            codigos_conexion(m.en_mascara, m.suficientes, m.desconectada),
            grilla,
        ),
        TipoArtefacto.P_ERROR: capa_continua(m.p_error, grilla, colores=NARANJAS[::-1]),
        TipoArtefacto.CAMBIO: capa_continua(
            m.delta, grilla, colores=NARANJAS, rango=RANGO_CAMBIO
        ),
    }

    for tipo, capa in capas.items():
        registrar_capa(corrida, tipo, capa, usuario)

    geotiffs: dict[str, tuple[Arreglo, bool]] = {
        TipoArtefacto.GEOTIFF_IF_ALTA: (m.if_alta, False),
        TipoArtefacto.GEOTIFF_IF: (m.if_total, False),
        TipoArtefacto.GEOTIFF_DESCONEXION: (
            codigos_conexion(m.en_mascara, m.suficientes, m.desconectada),
            True,
        ),
        TipoArtefacto.GEOTIFF_P_ERROR: (m.p_error, False),
        TipoArtefacto.GEOTIFF_CAMBIO: (m.delta, False),
        TipoArtefacto.GEOTIFF_CLASE_TIPICA: (m.tipica, True),
    }

    for tipo, (valores, entero) in geotiffs.items():
        registrar(
            corrida,
            tipo=tipo,
            formato=FormatoArtefacto.TIF,
            contenido=geotiff(
                asarray(valores, dtype=uint8 if entero else float64),
                grilla,
                entero=entero,
            ),
            usuario=usuario,
        )

    registrar(
        corrida,
        tipo=TipoArtefacto.RESUMEN_CSV,
        formato=FormatoArtefacto.CSV,
        contenido=resumen_csv(corrida).encode(),
        usuario=usuario,
    )

    if corrida.estanques.exists():  # ty: ignore[unresolved-attribute]
        registrar(
            corrida,
            tipo=TipoArtefacto.ESTANQUES,
            formato=FormatoArtefacto.GEOJSON,
            contenido=json_bytes(estanques(corrida)),
            usuario=usuario,
        )

    for tipo, objeto in (
        (TipoArtefacto.METADATOS, metodo(corrida)),
        (TipoArtefacto.RESUMEN, resumen(corrida)),
        (TipoArtefacto.MANIFIESTO, manifiesto(corrida, Base.ESTATICO)),
    ):
        registrar(
            corrida,
            tipo=tipo,
            formato=FormatoArtefacto.JSON,
            contenido=json_bytes(objeto),
            usuario=usuario,
        )


@atomic
def publicar(corrida: Corrida, usuario: ApiUser) -> Corrida:
    if corrida.estado != EstadoCorrida.COMPLETADA:
        raise CorridaInvalidaError(
            f"Solo se publica una corrida completada, no {corrida.estado}."
        )

    generar_artefactos(corrida, usuario)

    corrida.estado = EstadoCorrida.PUBLICADA  # ty: ignore[invalid-assignment]
    corrida.publicada_at = now()
    corrida.publicada_por = usuario  # ty: ignore[invalid-assignment]
    corrida.vigente = True  # ty: ignore[invalid-assignment]
    corrida.save(update_fields=["estado", "publicada_at", "publicada_por", "vigente"])

    escribir_vigente(corrida)

    return corrida


def proponer_relato(corrida: Corrida, usuario: ApiUser) -> Artefacto:
    if corrida.estado != EstadoCorrida.PUBLICADA:
        raise CorridaInvalidaError(
            f"Solo se propone el relato de una corrida publicada, no {corrida.estado}."
        )

    if corrida.artefactos.filter(tipo=TipoArtefacto.RELATO).exists():  # ty: ignore[unresolved-attribute]
        raise CorridaInvalidaError(f"La versión {corrida.version} ya tiene relato.")

    grilla: Grilla = corrida.region.grilla()  # ty: ignore[unresolved-attribute]

    return registrar(
        corrida,
        tipo=TipoArtefacto.RELATO,
        formato=FormatoArtefacto.JSON,
        contenido=json_bytes(relato(corrida, matrices(corrida, grilla))),
        usuario=usuario,
    )


def retirar(corrida: Corrida, motivo: str) -> Corrida:
    retirada: Corrida = retirar_corrida(corrida, motivo)

    relevo: Corrida | None = Corrida.objects.filter(
        region=corrida.region, vigente=True
    ).first()

    if relevo is not None:
        escribir_vigente(relevo)

    return retirada


########################################################################################


def purgar_artefactos(corrida: Corrida) -> None:
    for artefacto in Artefacto.objects.filter(corrida=corrida).select_related("media"):
        borrar(artefacto.media)

    Artefacto.objects.filter(corrida=corrida).delete()


def purgar_corridas() -> int:
    purgadas: int = 0

    for corrida in Corrida.objects.filter(
        estado=EstadoCorrida.RETIRADA,
        purgar_despues_de__lte=now(),
    ).exclude(cubo_archivo=""):
        with atomic():
            purgar_artefactos(corrida)

            for modelo in (
                ResumenFecha,
                ResumenPais,
                PruebaHipotesis,
                ResultadoEstanque,
                ResultadoCelda,
                CorridaInsumo,
                CorridaFecha,
            ):
                modelo.objects.filter(corrida=corrida).delete()

            absoluta(corrida.cubo_archivo).unlink(missing_ok=True)

            corrida.cubo_archivo = ""
            corrida.cubo_sha256 = ""
            corrida.save(update_fields=["cubo_archivo", "cubo_sha256"])

        LOG.info("Corrida %s purgada.", corrida.id)

        purgadas += 1

    return purgadas

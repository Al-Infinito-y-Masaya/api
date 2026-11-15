from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from logging import getLogger
from typing import TYPE_CHECKING

from asf_search import DATASET, ASFSession, search
from django.db import IntegrityError
from django.db.models import Q
from django.db.transaction import atomic
from django.utils.timezone import now
from h5py import File
from numpy import asarray
from pglock import advisory

from mangroove_adquisiciones.enums import (
    EstadoRecorte,
    EstadoSincronizacion,
    Madurez,
    OrigenSincronizacion,
)
from mangroove_adquisiciones.models import (
    Adquisicion,
    AdquisicionRecorte,
    Producto,
    Recorte,
    Sincronizacion,
)
from mangroove_comun.archivos import guardar_arreglo, leer_arreglo
from mangroove_comun.config import MANGROOVE_CONFIG
from mangroove_insumos.services import estimar_mareas
from mangroove_motor.agregacion import Agregado, agregar, cobertura
from mangroove_motor.lectura import ArchivoRemoto, ArchivoS3, CredencialesS3, usar_s3
from mangroove_motor.recorte import (
    MetadatosGranulo,
    ProductoInvalidoError,
    Recorte as RecorteMotor,
    escribir_recorte,
    leer_recorte,
    leer_ventana,
    parsear_granulo,
)
from mangroove_regiones.services import dentro_aoi

if TYPE_CHECKING:
    from pathlib import Path

    from api_auth.models import ApiUser
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo
    from mangroove_regiones.models import Region

########################################################################################

LOG = getLogger(__name__)

MADUREZ_ASF: dict[Madurez, str] = {
    Madurez.BETA: "BETA",
    Madurez.PROVISIONAL: "PROVISIONAL",
    Madurez.VALIDADO: "VALIDATED",
}

COLECCIONES: dict[Madurez, str] = {
    Madurez.BETA: "NISAR_L2_GCOV_BETA_V1",
    Madurez.PROVISIONAL: "NISAR_L2_GCOV_PROVISIONAL_V1",
    Madurez.VALIDADO: "NISAR_L2_GCOV_V1",
}

SEGUNDOS_PASADA: int = 120

########################################################################################


class SincronizacionEnCursoError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProductoEncontrado:
    metadatos: MetadatosGranulo
    madurez: Madurez
    https_url: str
    s3_url: str
    bytes: int | None
    procesado_at: datetime | None

    @property
    def pasada(self) -> tuple[int, str, str]:
        return (
            self.metadatos.track,
            self.metadatos.orbita,
            self.metadatos.inicio.strftime("%Y%m%dT%H%M"),
        )


type Buscador = Callable[[Region, date, date], list[ProductoEncontrado]]
type Apertura = Callable[[Producto], ArchivoRemoto]

########################################################################################


def desde_asf(resultado: object, madurez: Madurez) -> ProductoEncontrado | None:
    propiedades: dict = getattr(resultado, "properties", {})

    urls: list[str] = [
        propiedades.get("url") or "",
        *(propiedades.get("additionalUrls") or []),
    ]

    https: str = next(
        (u for u in urls if u.split("?", maxsplit=1)[0].endswith(".h5")), urls[0]
    )

    try:
        metadatos: MetadatosGranulo = parsear_granulo(
            https or propiedades.get("fileName", "")
        )
    except ProductoInvalidoError:
        return None

    s3: str = next(
        (
            u
            for u in propiedades.get("s3Urls") or []
            if u.endswith(".h5") and not u.endswith("_QA_STATS.h5")
        ),
        "",
    )

    tamano = propiedades.get("bytes")

    if isinstance(tamano, dict):
        tamano = next(
            (
                v.get("bytes") if isinstance(v, dict) else v
                for k, v in tamano.items()
                if k.endswith(".h5")
            ),
            None,
        )

    procesado: str | None = propiedades.get("processingDate")

    return ProductoEncontrado(
        metadatos=metadatos,
        madurez=madurez,
        https_url=https,
        s3_url=s3,
        bytes=int(tamano) if tamano else None,
        procesado_at=datetime.fromisoformat(procesado) if procesado else None,
    )


def buscar_productos(
    region: Region, desde: date, hasta: date
) -> list[ProductoEncontrado]:
    encontrados: list[ProductoEncontrado] = []

    for madurez, etiqueta in MADUREZ_ASF.items():
        resultados = search(
            dataMaturity=etiqueta,  # ty: ignore[invalid-argument-type]
            dataset=DATASET.NISAR,
            end=hasta.isoformat(),
            intersectsWith=region.aoi_wkt,  # ty: ignore[invalid-argument-type]
            processingLevel="GCOV",
            start=desde.isoformat(),
        )

        for resultado in resultados:
            producto: ProductoEncontrado | None = desde_asf(resultado, madurez)

            if producto is not None:
                encontrados.append(producto)

    return encontrados


def sesion_earthdata() -> ASFSession:
    sesion: ASFSession = ASFSession()

    token: str = MANGROOVE_CONFIG.EARTHDATA_TOKEN.get_secret_value().strip()

    if token:
        sesion.auth_with_token(token.removeprefix("Bearer ").strip())

    return sesion


def abridor() -> Apertura:
    sesion: ASFSession = sesion_earthdata()

    s3: bool = usar_s3(MANGROOVE_CONFIG.MANGROOVE_ACCESO)

    credenciales: CredencialesS3 | None = CredencialesS3(sesion) if s3 else None

    hilos: int = MANGROOVE_CONFIG.MANGROOVE_HILOS or (16 if s3 else 6)

    def abrir(producto: Producto) -> ArchivoRemoto:
        if credenciales is not None and producto.s3_url:
            return ArchivoS3(producto.s3_url, credenciales, hilos=hilos)  # ty: ignore[invalid-argument-type]

        return ArchivoRemoto(producto.https_url, sesion, hilos=hilos)  # ty: ignore[invalid-argument-type]

    return abrir


########################################################################################


def vigente_de_pasada(
    region: Region, track: int, orbita: str, inicio: datetime
) -> Adquisicion | None:
    return (
        Adquisicion.objects
        .filter(region=region, track=track, orbita=orbita, reemplazada=False)
        .filter(pasada_at=inicio.replace(second=0, microsecond=0))
        .first()
    )


def registrar(
    region: Region, encontrados: Iterable[ProductoEncontrado]
) -> tuple[int, int]:
    mejores: dict[tuple[int, str, str, int], ProductoEncontrado] = {}

    for p in encontrados:
        clave: tuple[int, str, str, int] = (*p.pasada, p.metadatos.frame)

        actual: ProductoEncontrado | None = mejores.get(clave)

        if actual is None or p.metadatos.crid > actual.metadatos.crid:
            mejores[clave] = p

    elegidos: set[str] = {p.metadatos.granulo for p in mejores.values()}

    nuevos: int = 0
    descartados: int = 0

    for p in encontrados:
        producto, _ = Producto.objects.get_or_create(
            granulo=p.metadatos.granulo,
            defaults={
                "bytes": p.bytes,
                "ciclo": p.metadatos.ciclo,
                "coleccion": COLECCIONES[p.madurez],
                "crid": p.metadatos.crid,
                "fin_at": p.metadatos.fin,
                "frame": p.metadatos.frame,
                "https_url": p.https_url,
                "inicio_at": p.metadatos.inicio,
                "madurez": p.madurez,
                "orbita": p.metadatos.orbita,
                "polarizaciones": p.metadatos.polarizaciones,
                "procesado_at": p.procesado_at,
                "s3_url": p.s3_url,
                "track": p.metadatos.track,
            },
        )

        if Recorte.objects.filter(producto=producto, region=region).exists():
            continue

        motivo: str = motivo_descarte(region, p, elegidos)

        Recorte.objects.create(
            producto=producto,
            region=region,
            estado=EstadoRecorte.DESCARTADO if motivo else EstadoRecorte.PENDIENTE,
            motivo_descarte=motivo,
        )

        if motivo:
            descartados += 1
        else:
            nuevos += 1

    return nuevos, descartados


def motivo_descarte(region: Region, p: ProductoEncontrado, elegidos: set[str]) -> str:
    if p.metadatos.granulo not in elegidos:
        return "Hay una versión más reciente de esta pasada en la misma búsqueda."

    vigente: Adquisicion | None = vigente_de_pasada(
        region,
        p.metadatos.track,
        p.metadatos.orbita,
        p.metadatos.inicio,
    )

    if vigente is not None and vigente.crid >= p.metadatos.crid:
        return f"Ya hay una adquisición con CRID {vigente.crid} para esta pasada."

    return ""


########################################################################################


def recortar(region: Region, recorte: Recorte, abrir: Apertura) -> int:
    producto: Producto = recorte.producto  # ty: ignore[invalid-assignment]

    archivo: ArchivoRemoto | None = None

    try:
        archivo = abrir(producto)

        with File(archivo, "r") as h5:
            ventana: RecorteMotor | None = leer_ventana(
                h5,
                region.grilla(),
                archivo=archivo,
                granulo=producto.granulo,  # ty: ignore[invalid-argument-type]
                margen_m=float(region.margen_m),  # ty: ignore[invalid-argument-type]
            )
    except ProductoInvalidoError as e:
        descartar(recorte, str(e))

        return 0
    except Exception as e:  # ruff: ignore[blind-except]
        LOG.warning("Falló el recorte de %s: %s", producto.granulo, e)

        recorte.estado = EstadoRecorte.FALLIDO  # ty: ignore[invalid-assignment]
        recorte.intentos += 1  # ty: ignore[unsupported-operator]
        recorte.error = f"{type(e).__name__}: {e}"[:2000]  # ty: ignore[invalid-assignment]
        recorte.save(update_fields=["estado", "intentos", "error"])

        return 0
    finally:
        if archivo is not None:
            archivo.close()

    if ventana is None:
        descartar(recorte, "El producto no cubre la región.")

        return archivo.transferido if archivo else 0

    destino: Path = MANGROOVE_CONFIG.recortes / region.codigo / f"{producto.granulo}.h5"  # ty: ignore[unsupported-operator]

    escrito = escribir_recorte(destino, ventana, producto.https_url)  # ty: ignore[invalid-argument-type]

    recorte.estado = EstadoRecorte.RECORTADO  # ty: ignore[invalid-assignment]
    recorte.archivo = str(destino.relative_to(MANGROOVE_CONFIG.MANGROOVE_DATOS))  # ty: ignore[invalid-assignment]
    recorte.sha256 = escrito.sha256  # ty: ignore[invalid-assignment]
    recorte.bytes = escrito.bytes  # ty: ignore[invalid-assignment]
    recorte.ventana = [*ventana.ventana.filas, *ventana.ventana.columnas]  # ty: ignore[invalid-assignment]
    recorte.pixel_m = ventana.pixel_m  # ty: ignore[invalid-assignment]
    recorte.epsg_nativo = ventana.epsg  # ty: ignore[invalid-assignment]
    recorte.incidencia = ventana.incidencia  # ty: ignore[invalid-assignment]
    recorte.recortado_at = now()
    recorte.error = ""  # ty: ignore[invalid-assignment]
    recorte.save()

    return archivo.transferido if archivo else 0


def descartar(recorte: Recorte, motivo: str) -> None:
    recorte.estado = EstadoRecorte.DESCARTADO  # ty: ignore[invalid-assignment]
    recorte.motivo_descarte = motivo[:2000]  # ty: ignore[invalid-assignment]
    recorte.save(update_fields=["estado", "motivo_descarte"])


########################################################################################


def grupos_de_pasada(recortes: list[Recorte]) -> list[list[Recorte]]:
    ordenados: list[Recorte] = sorted(
        recortes,
        key=lambda r: (
            r.producto.track,  # ty: ignore[unresolved-attribute]
            r.producto.orbita,  # ty: ignore[unresolved-attribute]
            r.producto.crid,  # ty: ignore[unresolved-attribute]
            r.producto.inicio_at,  # ty: ignore[unresolved-attribute]
        ),
    )

    grupos: list[list[Recorte]] = []

    for recorte in ordenados:
        p: Producto = recorte.producto  # ty: ignore[invalid-assignment]

        if grupos:
            q: Producto = grupos[-1][0].producto  # ty: ignore[invalid-assignment]

            if (p.track, p.orbita, p.crid) == (q.track, q.orbita, q.crid) and abs(
                (p.inicio_at - q.inicio_at).total_seconds()  # ty: ignore[unsupported-operator]
            ) < SEGUNDOS_PASADA:
                grupos[-1].append(recorte)
                continue

        grupos.append([recorte])

    return grupos


def agregar_grupo(grupo: list[Recorte], grilla: Grilla) -> tuple[Arreglo, float | None]:
    total: Agregado | None = None
    incidencias: list[float] = []

    for recorte in grupo:
        datos: RecorteMotor = leer_recorte(
            MANGROOVE_CONFIG.MANGROOVE_DATOS / recorte.archivo  # ty: ignore[unsupported-operator]
        )

        agregado: Agregado = agregar(
            hh=datos.hh,
            hv=datos.hv,
            xs=datos.xs,
            ys=datos.ys,
            epsg=datos.epsg,
            grilla=grilla,
            mascara=datos.mascara,
            estricta=recorte.mascara_modo == "estricta",
        )

        total = agregado if total is None else total + agregado

        if datos.incidencia is not None:
            incidencias.append(datos.incidencia)

    if total is None:
        raise ValueError("Un grupo de pasada no puede estar vacío.")

    incidencia: float | None = (
        round(sum(incidencias) / len(incidencias), 2) if incidencias else None
    )

    return total.en_db(), incidencia


@atomic
def consolidar(region: Region) -> list[Adquisicion]:
    sueltos: list[Recorte] = list(
        Recorte.objects
        .filter(region=region, estado=EstadoRecorte.RECORTADO)
        .exclude(id__in=AdquisicionRecorte.objects.values("recorte_id"))
        .select_related("producto"),
    )

    grilla: Grilla = region.grilla()
    adentro: Arreglo = dentro_aoi(region)

    creadas: list[Adquisicion] = []

    for grupo in grupos_de_pasada(sueltos):
        primero: Producto = min((r.producto for r in grupo), key=lambda p: p.inicio_at)  # ty: ignore[no-matching-overload]

        anterior: Adquisicion | None = vigente_de_pasada(
            region,
            primero.track,  # ty: ignore[invalid-argument-type]
            primero.orbita,  # ty: ignore[invalid-argument-type]
            primero.inicio_at,  # ty: ignore[invalid-argument-type]
        )

        if anterior is not None and anterior.crid >= primero.crid:
            LOG.warning(
                "Se omite %s: la pasada ya tiene CRID %s.",
                primero.granulo,
                anterior.crid,
            )
            continue

        db, incidencia = agregar_grupo(grupo, grilla)

        guardado = guardar_arreglo(
            MANGROOVE_CONFIG.grillas / region.codigo / f"{primero.granulo}.npy",  # ty: ignore[unsupported-operator]
            db,
        )

        adquisicion: Adquisicion = Adquisicion.objects.create(
            region=region,
            track=primero.track,
            orbita=primero.orbita,
            frames=sorted({r.producto.frame for r in grupo}),  # ty: ignore[unresolved-attribute]
            inicio_at=primero.inicio_at,
            madurez=primero.madurez,
            crid=primero.crid,
            incidencia=incidencia,
            cobertura=round(cobertura(db, adentro), 4),
            grilla_archivo=guardado.relativa,
            grilla_sha256=guardado.sha256,
            reemplaza_a=anterior,
        )

        AdquisicionRecorte.objects.bulk_create(
            [AdquisicionRecorte(adquisicion=adquisicion, recorte=r) for r in grupo],
        )

        creadas.append(adquisicion)

    return creadas


########################################################################################


def sincronizar(  # ruff: ignore[too-many-arguments]
    region: Region,
    *,
    desde: date,
    hasta: date,
    usuario: ApiUser | None = None,
    buscador: Buscador = buscar_productos,
    apertura: Callable[[], Apertura] = abridor,
) -> Sincronizacion:
    with advisory(f"mangroove.sincronizar.{region.id}", timeout=0) as obtenido:
        if not obtenido:
            raise SincronizacionEnCursoError(
                f"Ya hay una sincronización en curso de {region.codigo}."
            )

        try:
            sincronizacion: Sincronizacion = Sincronizacion.objects.create(
                region=region,
                origen=OrigenSincronizacion.MANUAL
                if usuario
                else OrigenSincronizacion.PROGRAMADA,
                solicitada_por=usuario,
            )
        except IntegrityError as e:
            raise SincronizacionEnCursoError(
                f"Ya hay una sincronización en curso de {region.codigo}.",
            ) from e

        try:  # ruff: ignore[too-many-statements-in-try-clause]
            encontrados: list[ProductoEncontrado] = buscador(region, desde, hasta)

            nuevos, _ = registrar(region, encontrados)

            pendientes = Recorte.objects.filter(
                Q(estado=EstadoRecorte.PENDIENTE)
                | Q(estado=EstadoRecorte.FALLIDO, intentos__lt=3),
                region=region,
            ).select_related("producto")

            transferidos: int = 0
            abrir: Apertura | None = None

            for recorte in pendientes:
                abrir = abrir or apertura()
                transferidos += recortar(region, recorte, abrir)

            adquisiciones: list[Adquisicion] = consolidar(region)

            estimar_mareas(region, adquisiciones)

            sincronizacion.n_encontrados = len(encontrados)  # ty: ignore[invalid-assignment]
            sincronizacion.n_recortados = Recorte.objects.filter(
                region=region,
                estado=EstadoRecorte.RECORTADO,
                recortado_at__gte=sincronizacion.inicio_at,
            ).count()
            sincronizacion.n_descartados = Recorte.objects.filter(
                region=region,
                estado=EstadoRecorte.DESCARTADO,
                updated_at__gte=sincronizacion.inicio_at,
            ).count()
            sincronizacion.n_fallidos = Recorte.objects.filter(
                region=region,
                estado=EstadoRecorte.FALLIDO,
            ).count()
            sincronizacion.bytes_transferidos = transferidos  # ty: ignore[invalid-assignment]
            sincronizacion.estado = EstadoSincronizacion.COMPLETADA  # ty: ignore[invalid-assignment]
        except Exception as e:
            sincronizacion.estado = EstadoSincronizacion.FALLIDA  # ty: ignore[invalid-assignment]
            sincronizacion.error = f"{type(e).__name__}: {e}"[:2000]  # ty: ignore[invalid-assignment]

            raise
        finally:
            sincronizacion.fin_at = now()
            sincronizacion.save()

        LOG.info(
            "Sincronización de %s: %s nuevos, %s adquisiciones.",
            region.codigo,
            nuevos,
            len(adquisiciones),
        )

    return sincronizacion


def grilla_de(adquisicion: Adquisicion) -> Arreglo:
    return asarray(leer_arreglo(adquisicion.grilla_archivo))  # ty: ignore[invalid-argument-type]

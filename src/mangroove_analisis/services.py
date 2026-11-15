from datetime import date, timedelta
from io import BytesIO
from logging import getLogger
from math import isfinite as finito
from typing import TYPE_CHECKING

from django.db import connection
from django.db.transaction import atomic
from django.utils.timezone import now
from numpy import (
    asarray,
    float32,
    int16,
    isfinite,
    load,
    nan,
    round as np_round,
    savez,
    stack,
    where,
)

from mangroove_adquisiciones.enums import Madurez
from mangroove_adquisiciones.models import Adquisicion
from mangroove_analisis.enums import EstadoCorrida, MadurezCorrida, OrbitaCorrida
from mangroove_analisis.models import (
    Corrida,
    CorridaFecha,
    CorridaInsumo,
    PerfilUmbrales,
    PruebaHipotesis,
    ResultadoCelda,
    ResultadoEstanque,
    ResumenFecha,
    ResumenPais,
)
from mangroove_comun.archivos import absoluta, guardar_bytes, leer_arreglo
from mangroove_comun.config import MANGROOVE_CONFIG
from mangroove_insumos.enums import TipoInsumo
from mangroove_insumos.models import Estanque, EstimacionMarea, Insumo
from mangroove_insumos.services import auxiliares_de, lluvia_3d, vigentes
from mangroove_motor.analisis import Resultado, analizar
from mangroove_motor.auxiliares import codigos_a_indices
from mangroove_motor.cusum import Cambios
from mangroove_motor.datos import Auxiliares, Fecha, Pila
from mangroove_motor.perfil import Perfil, nivel_marea
from mangroove_regiones.services import ids_celdas

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import QuerySet

    from api_auth.models import ApiUser
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo
    from mangroove_regiones.models import Region

########################################################################################

LOG = getLogger(__name__)

ESCALA_DB: int = 100
ESCALA_COHERENCIA: int = 1000
SIN_DATO_DB: int = -32768

COLUMNAS_CELDA: tuple[str, ...] = (
    "corrida_id",
    "celda_id",
    "pais",
    "en_mascara",
    "humedal",
    "hh",
    "hv",
    "coherencia",
    "clases",
    "clase_tipica",
    "if_total",
    "if_alta",
    "n_fechas",
    "n_fechas_alta",
    "datos_suficientes",
    "desconectada",
    "p_error",
    "if_esperada",
    "cambio_orden",
    "cambio_confianza",
    "cambio_delta_hv_db",
)

TIPOS_CELDA: tuple[str, ...] = (
    "uuid",
    "uuid",
    "varchar",
    "bool",
    "bool",
    "int2[]",
    "int2[]",
    "int2[]",
    "int2[]",
    "int2",
    "float8",
    "float8",
    "int2",
    "int2",
    "bool",
    "bool",
    "float8",
    "float8",
    "int2",
    "float8",
    "float8",
)

PERFIL_PREDETERMINADO: str = "predeterminado"

########################################################################################


class CorridaInvalidaError(ValueError):
    pass


########################################################################################


def adquisiciones_elegibles(  # ruff: ignore[too-many-arguments]
    region: Region,
    *,
    madurez: str,
    orbita: str = OrbitaCorrida.AMBAS,
    tracks: Sequence[int] = (),
    desde: date | None = None,
    hasta: date | None = None,
) -> QuerySet[Adquisicion]:  # ty: ignore[invalid-type-form]
    qs: QuerySet[Adquisicion] = Adquisicion.objects.filter(  # ty: ignore[invalid-type-form]
        region=region,
        madurez=madurez,
        reemplazada=False,
        excluida=False,
    ).order_by("inicio_at", "track")

    if orbita != OrbitaCorrida.AMBAS:
        qs = qs.filter(orbita=orbita)

    if tracks:
        qs = qs.filter(track__in=list(tracks))

    if desde is not None:
        qs = qs.filter(inicio_at__date__gte=desde)

    if hasta is not None:
        qs = qs.filter(inicio_at__date__lte=hasta)

    return qs


def proponer_version(
    region: Region, adquisiciones: list[str], insumos: list[str], perfil_id: str
) -> str:
    anterior: Corrida | None = (
        Corrida.objects.filter(region=region).order_by("-created_at").first()
    )

    if anterior is None:
        return "1.0.0"

    mayor, menor, parche = (int(v) for v in anterior.version.split("."))  # ty: ignore[unresolved-attribute]

    previos: set[str] = {
        str(i)
        for i in anterior.insumos.values_list("insumo_id", flat=True)  # ty: ignore[unresolved-attribute]
    }

    datos_distintos: bool = [
        str(a)
        for a in anterior.fijadas  # ty: ignore[not-iterable]
    ] != adquisiciones or previos != set(insumos)

    if datos_distintos:
        candidata: tuple[int, int, int] = (mayor, menor + 1, 0)
    else:
        candidata = (mayor, menor, parche + 1)

    while Corrida.objects.filter(
        region=region, version="{}.{}.{}".format(*candidata)
    ).exists():
        candidata = (candidata[0], candidata[1], candidata[2] + 1)

    if str(anterior.perfil_id) == perfil_id and not datos_distintos:  # ty: ignore[unresolved-attribute]
        LOG.info(
            "La corrida nueva repite los datos y el perfil de %s.", anterior.version
        )

    return "{}.{}.{}".format(*candidata)


@atomic
def crear_corrida(  # ruff: ignore[too-many-arguments]
    region: Region,
    *,
    madurez: str,
    perfil: PerfilUmbrales | None = None,
    modelo_marea: str | None = None,
    fuente_lluvia: str = "",
    orbita: str = OrbitaCorrida.AMBAS,
    tracks: Sequence[int] = (),
    desde: date | None = None,
    hasta: date | None = None,
    usuario: ApiUser | None = None,
) -> Corrida:
    if madurez not in MadurezCorrida.values:
        raise CorridaInvalidaError(f"Una corrida no admite la madurez {madurez!r}.")

    elegido: PerfilUmbrales = perfil or perfil_vigente(PERFIL_PREDETERMINADO)

    adquisiciones: list[str] = [
        str(i)
        for i in adquisiciones_elegibles(
            region,
            madurez=madurez,
            orbita=orbita,
            tracks=tracks,
            desde=desde,
            hasta=hasta,
        ).values_list("id", flat=True)
    ]

    if not adquisiciones:
        raise CorridaInvalidaError("No hay adquisiciones vigentes para esa selección.")

    insumos: list[Insumo] = list(vigentes(region).values())

    corrida: Corrida = Corrida.objects.create(
        region=region,
        version=proponer_version(
            region,
            adquisiciones,
            [str(i.id) for i in insumos],
            str(elegido.id),
        ),
        perfil=elegido,
        madurez=madurez,
        modelo_marea=modelo_marea or MANGROOVE_CONFIG.MANGROOVE_MODELO_MAREA,
        fuente_lluvia=fuente_lluvia,
        orbita=orbita,
        tracks=list(tracks),
        desde=desde,
        hasta=hasta,
        codigo_version=MANGROOVE_CONFIG.MANGROOVE_CODIGO,
        n_fechas=len(adquisiciones),
        fijadas=adquisiciones,
        solicitada_por=usuario,
    )

    CorridaInsumo.objects.bulk_create(
        [CorridaInsumo(corrida=corrida, insumo=insumo) for insumo in insumos],
    )

    return corrida


def perfil_vigente(codigo: str) -> PerfilUmbrales:
    perfil: PerfilUmbrales | None = (
        PerfilUmbrales.objects.filter(codigo=codigo).order_by("-version").first()
    )

    if perfil is None:
        raise CorridaInvalidaError(f"No existe el perfil {codigo!r}.")

    return perfil


def proponer_corrida(region: Region) -> Corrida | None:
    vigentes_qs = Adquisicion.objects.filter(
        region=region, reemplazada=False, excluida=False
    )

    if vigentes_qs.filter(madurez=Madurez.VALIDADO).exists():
        madurez: str = Madurez.VALIDADO
    elif vigentes_qs.filter(madurez=Madurez.PROVISIONAL).exists():
        madurez = Madurez.PROVISIONAL
    else:
        return None

    if Corrida.objects.filter(region=region, estado=EstadoCorrida.PENDIENTE).exists():
        return None

    return crear_corrida(region, madurez=madurez)


########################################################################################


def fechas_de(corrida: Corrida, adquisiciones: list[Adquisicion]) -> tuple[Fecha, ...]:
    mareas: dict[str, float] = dict(
        EstimacionMarea.objects.filter(
            adquisicion__in=adquisiciones,
            modelo=corrida.modelo_marea,
        ).values_list("adquisicion_id", "altura_m"),
    )

    return tuple(
        Fecha(
            track=a.track,  # ty: ignore[invalid-argument-type]
            marea_m=mareas.get(a.id),
            lluvia_3d_mm=lluvia_3d(corrida.region, a.inicio_at, corrida.fuente_lluvia),  # ty: ignore[invalid-argument-type]
        )
        for a in adquisiciones
    )


def pila_de(corrida: Corrida) -> tuple[Pila, list[Adquisicion]]:
    por_id: dict[str, Adquisicion] = {
        str(a.id): a for a in Adquisicion.objects.filter(id__in=corrida.fijadas)
    }

    adquisiciones: list[Adquisicion] = [por_id[str(i)] for i in corrida.fijadas]  # ty: ignore[not-iterable]

    grillas: Arreglo = stack([
        asarray(leer_arreglo(a.grilla_archivo))  # ty: ignore[invalid-argument-type]
        for a in adquisiciones
    ])

    return (
        Pila(
            hh=grillas[:, 0].astype(float32),
            hv=grillas[:, 1].astype(float32),
            fechas=fechas_de(corrida, adquisiciones),
        ),
        adquisiciones,
    )


def a_entero(valores: Arreglo, escala: int) -> Arreglo:
    datos: Arreglo = asarray(valores, dtype=float32)

    return where(isfinite(datos), np_round(datos * escala), SIN_DATO_DB).astype(int16)


def opcional(valor: float) -> float | None:
    return float(valor) if finito(float(valor)) else None


def filas_celdas(
    corrida: Corrida,
    resultado: Resultado,
    auxiliares: Auxiliares,
    grilla: Grilla,
) -> list[tuple]:
    ids: Arreglo = ids_celdas(corrida.region)  # ty: ignore[invalid-argument-type]

    hh: Arreglo = a_entero(resultado.calibrado.hh, ESCALA_DB)
    hv: Arreglo = a_entero(resultado.calibrado.hv, ESCALA_DB)
    clases: Arreglo = resultado.clasificacion.clases
    paises: list[str] = (
        [""] * grilla.n
        if auxiliares.paises is None
        else codigos_a_indices(auxiliares.codigos_paises, auxiliares.paises)
    )

    frec = resultado.frecuencias
    cambios: Cambios = resultado.cambios
    esperada: Arreglo | None = resultado.if_esperada

    filas: list[tuple] = []

    for i in range(grilla.n):
        mascara: bool = bool(resultado.en_mascara[i])
        cambio: bool = mascara and bool(cambios.significativo[i])

        filas.append(
            (
                corrida.id,
                ids[i],
                paises[i],
                mascara,
                bool(resultado.humedal[i]),
                hh[:, i].tolist(),
                hv[:, i].tolist(),
                [],
                clases[:, i].tolist(),
                int(resultado.clasificacion.tipica[i]),
                opcional(frec.if_total[i]) if mascara else None,
                opcional(frec.if_alta[i]) if mascara else None,
                int(frec.n_fechas[i]),
                int(frec.n_fechas_alta[i]),
                mascara and bool(frec.datos_suficientes[i]),
                mascara and bool(resultado.desconectada[i]),
                opcional(resultado.clasificacion.p_error[i]) if mascara else None,
                opcional(esperada[i]) if mascara and esperada is not None else None,
                int(cambios.orden[i]) if cambio else None,
                opcional(cambios.confianza[i]) if cambio else None,
                opcional(cambios.delta_hv_db[i]) if cambio else None,
            ),
        )

    return filas


def copiar_celdas(filas: list[tuple]) -> None:
    tabla: str = ResultadoCelda._meta.db_table  # ruff: ignore[private-member-access]

    sql: str = f"COPY {tabla} ({', '.join(COLUMNAS_CELDA)}) FROM STDIN (FORMAT BINARY)"

    with connection.cursor() as cursor, cursor.cursor.copy(sql) as copia:
        copia.set_types(list(TIPOS_CELDA))

        for fila in filas:
            copia.write_row(fila)


def guardar_cubo(corrida: Corrida, pila: Pila, resultado: Resultado) -> None:
    buffer: BytesIO = BytesIO()

    savez(
        buffer,
        cambio_confianza=resultado.cambios.confianza,
        cambio_delta=resultado.cambios.delta_hv_db,
        cambio_orden=resultado.cambios.orden,
        cambio_significativo=resultado.cambios.significativo,
        hh=a_entero(pila.hh, ESCALA_DB),
        hv=a_entero(pila.hv, ESCALA_DB),
    )

    guardado = guardar_bytes(
        MANGROOVE_CONFIG.cubos / corrida.region.codigo / f"{corrida.version}.npz",  # ty: ignore[unresolved-attribute]
        buffer.getvalue(),
    )

    corrida.cubo_archivo = guardado.relativa  # ty: ignore[invalid-assignment]
    corrida.cubo_sha256 = guardado.sha256  # ty: ignore[invalid-assignment]


def cubo_de(corrida: Corrida) -> tuple[Arreglo, Arreglo, Cambios]:
    with load(absoluta(corrida.cubo_archivo), allow_pickle=False) as datos:  # ty: ignore[invalid-argument-type]
        hh: Arreglo = where(datos["hh"] == SIN_DATO_DB, nan, datos["hh"] / ESCALA_DB)
        hv: Arreglo = where(datos["hv"] == SIN_DATO_DB, nan, datos["hv"] / ESCALA_DB)

        cambios: Cambios = Cambios(
            orden=datos["cambio_orden"],
            confianza=datos["cambio_confianza"],
            delta_hv_db=datos["cambio_delta"],
            significativo=datos["cambio_significativo"],
        )

    return hh.astype(float32), hv.astype(float32), cambios


@atomic
def persistir(  # ruff: ignore[too-many-arguments]
    corrida: Corrida,
    *,
    pila: Pila,
    adquisiciones: list[Adquisicion],
    auxiliares: Auxiliares,
    resultado: Resultado,
    perfil: Perfil,
) -> None:
    fechas: list[CorridaFecha] = CorridaFecha.objects.bulk_create(
        [
            CorridaFecha(
                corrida=corrida,
                adquisicion=adquisicion,
                orden=orden,
                desfase_hh_db=round(float(resultado.calibrado.desfase_hh[orden]), 4),
                desfase_hv_db=round(float(resultado.calibrado.desfase_hv[orden]), 4),
                marea_m=fecha.marea_m,
                marea_nivel=nivel_marea(perfil, fecha.marea_m).value,
                lluvia_3d_mm=fecha.lluvia_3d_mm,
                usada_en_if_alta=bool(resultado.usadas_alta[orden]),
            )
            for orden, (adquisicion, fecha) in enumerate(
                zip(adquisiciones, pila.fechas, strict=True)
            )
        ],
    )

    grilla: Grilla = corrida.region.grilla()  # ty: ignore[unresolved-attribute]

    copiar_celdas(filas_celdas(corrida, resultado, auxiliares, grilla))

    ResumenPais.objects.bulk_create(
        [
            ResumenPais(
                corrida=corrida,
                pais=r.pais,
                n_celdas=r.n_celdas,
                ha_manglar=r.ha_manglar,
                ha_desconectada=r.ha_desconectada,
                ha_insuficiente=r.ha_insuficiente,
                ha_perdida_copa=r.ha_perdida_copa,
                ha_iv_tipica=r.ha_iv_tipica,
                ha_ow_tipica=r.ha_ow_tipica,
                ha_ni_tipica=r.ha_ni_tipica,
            )
            for r in resultado.resumen_pais
        ],
    )

    ResumenFecha.objects.bulk_create(
        [
            ResumenFecha(
                corrida=corrida,
                corrida_fecha=fechas[r.orden],
                pais=r.pais,
                ha_iv=r.ha_iv,
                ha_ow=r.ha_ow,
                ha_ni=r.ha_ni,
                ha_nc=r.ha_nc,
                ha_nd=r.ha_nd,
            )
            for r in resultado.resumen_fecha
        ],
    )

    PruebaHipotesis.objects.bulk_create(
        [
            PruebaHipotesis(
                corrida=corrida,
                codigo=h.codigo,
                prueba=h.prueba.value,
                grupo_a=h.grupo_a,
                grupo_b=h.grupo_b,
                evaluable=h.evaluable,
                motivo=h.motivo,
                n_a=h.n_a,
                n_b=h.n_b,
                mediana_a=h.mediana_a,
                mediana_b=h.mediana_b,
                estadistico=h.estadistico,
                z=h.z,
                p_valor=h.p_valor,
                efecto=h.efecto,
            )
            for h in resultado.hipotesis
        ],
    )

    insumo_estanques: CorridaInsumo | None = corrida.insumos.filter(  # ty: ignore[unresolved-attribute]
        tipo=TipoInsumo.ESTANQUES,
    ).first()

    if insumo_estanques is not None and resultado.estanques:
        por_numero: dict[int, Estanque] = {
            e.numero: e
            for e in Estanque.objects.filter(insumo_id=insumo_estanques.insumo_id)  # ty: ignore[unresolved-attribute]
        }

        ResultadoEstanque.objects.bulk_create(
            [
                ResultadoEstanque(
                    corrida=corrida,
                    estanque=por_numero[r.numero],
                    area_ha=round(r.area_ha, 4),
                    cv_hh=opcional(r.cv_hh),
                    cv_hv=opcional(r.cv_hv),
                    cv=opcional(r.cv),
                    activo=r.activo,
                    dist_canal_km=opcional(r.dist_canal_km),
                    if_vecino=r.if_vecino,
                    puntaje=r.puntaje,
                )
                for r in resultado.estanques
                if r.numero in por_numero
            ],
        )

    guardar_cubo(corrida, pila, resultado)

    corrida.estado = EstadoCorrida.COMPLETADA  # ty: ignore[invalid-assignment]
    corrida.terminada_at = now()
    corrida.save(
        update_fields=["estado", "terminada_at", "cubo_archivo", "cubo_sha256"]
    )


def calcular(corrida: Corrida) -> Corrida:
    try:  # ruff: ignore[too-many-statements-in-try-clause]
        pila, adquisiciones = pila_de(corrida)

        grilla: Grilla = corrida.region.grilla()  # ty: ignore[unresolved-attribute]

        auxiliares: Auxiliares = auxiliares_de(
            (
                ci.insumo
                for ci in corrida.insumos.select_related("insumo", "insumo__region")  # ty: ignore[unresolved-attribute]
            ),
            grilla,
        )

        perfil: Perfil = corrida.perfil.a_perfil()  # ty: ignore[unresolved-attribute]

        resultado: Resultado = analizar(
            pila=pila,
            auxiliares=auxiliares,
            grilla=grilla,
            perfil=perfil,
            semilla=corrida.semilla,  # ty: ignore[invalid-argument-type]
        )

        persistir(
            corrida,
            pila=pila,
            adquisiciones=adquisiciones,
            auxiliares=auxiliares,
            resultado=resultado,
            perfil=perfil,
        )
    except Exception as e:
        LOG.exception("Falló la corrida %s.", corrida.id)

        corrida.refresh_from_db()
        corrida.estado = EstadoCorrida.FALLIDA  # ty: ignore[invalid-assignment]
        corrida.terminada_at = now()
        corrida.error = f"{type(e).__name__}: {e}"[:2000]  # ty: ignore[invalid-assignment]
        corrida.save(update_fields=["estado", "terminada_at", "error"])

        raise

    return corrida


def iniciar(corrida: Corrida) -> None:
    corrida.estado = EstadoCorrida.EN_PROCESO  # ty: ignore[invalid-assignment]
    corrida.iniciada_at = now()
    corrida.save(update_fields=["estado", "iniciada_at"])


def ejecutar_corrida(corrida: Corrida) -> Corrida:
    iniciar(corrida)

    return calcular(corrida)


def ejecutar_pendientes() -> int:
    ejecutadas: int = 0

    while True:
        with atomic():
            corrida: Corrida | None = (
                Corrida.objects
                .select_for_update(skip_locked=True)
                .filter(estado=EstadoCorrida.PENDIENTE)
                .order_by("created_at")
                .first()
            )

            if corrida is None:
                return ejecutadas

            iniciar(corrida)

        try:
            calcular(corrida)
        except Exception:  # ruff: ignore[blind-except]
            LOG.warning("La corrida %s quedó fallida.", corrida.id)

        ejecutadas += 1


########################################################################################


@atomic
def retirar_corrida(corrida: Corrida, motivo: str) -> Corrida:
    if not motivo.strip():
        raise CorridaInvalidaError("Retirar una corrida exige un motivo.")

    corrida.refresh_from_db()

    corrida.estado = EstadoCorrida.RETIRADA  # ty: ignore[invalid-assignment]
    corrida.retirada_at = now()
    corrida.motivo_retiro = motivo.strip()  # ty: ignore[invalid-assignment]
    corrida.purgar_despues_de = corrida.retirada_at + timedelta(
        days=MANGROOVE_CONFIG.MANGROOVE_DIAS_PURGA,
    )
    corrida.save(
        update_fields=["estado", "retirada_at", "motivo_retiro", "purgar_despues_de"],
    )

    corrida.refresh_from_db()

    return corrida

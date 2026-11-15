from typing import TYPE_CHECKING

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import (
    ArrayField,
    DateTimeRangeField,
    RangeOperators,
)
from django.db.models import (
    RESTRICT,
    BigIntegerField,
    BooleanField,
    CharField,
    CheckConstraint,
    DateTimeField,
    F,
    FloatField,
    ForeignKey,
    Index,
    IntegerField,
    OneToOneField,
    Q,
    SmallIntegerField,
    TextField,
    UniqueConstraint,
)
from django.db.models.functions import Now
from django.utils.timezone import now
from pgtrigger import (
    Before,
    F as TriggerF,
    Insert,
    Protect,
    Q as TriggerQ,
    ReadOnly,
    Trigger,
    Update,
)

from api_auth.models import ApiUser
from api_core.models.base import ApiAppendOnlyModel, ApiProtectedModel
from api_utils.db import track_table
from mangroove_adquisiciones.enums import (
    EstadoRecorte,
    EstadoSincronizacion,
    Madurez,
    Orbita,
    OrigenSincronizacion,
)
from mangroove_regiones.models import Region

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import BaseConstraint
    from pgtrigger import Trigger as TriggerType

########################################################################################

PATRON_CRID: str = r"^P[0-9]{5}$"

PATRON_SHA256: str = r"^[0-9a-f]{64}$"

INTENTOS_MAXIMOS: int = 3

########################################################################################


class Producto(ApiAppendOnlyModel):
    granulo = CharField(max_length=150)
    coleccion = CharField(max_length=60)
    madurez = CharField(choices=Madurez.choices, max_length=12)
    crid = CharField(max_length=6)

    ciclo = SmallIntegerField()
    track = SmallIntegerField()
    frame = SmallIntegerField()
    orbita = CharField(choices=Orbita.choices, max_length=4)

    inicio_at = DateTimeField()
    fin_at = DateTimeField()
    procesado_at = DateTimeField(null=True)

    polarizaciones = CharField(max_length=4)
    s3_url = TextField(db_default="", default="")
    https_url = TextField()
    bytes = BigIntegerField(null=True)

    class Meta(ApiAppendOnlyModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(crid__regex=PATRON_CRID), name="chk_%(class)s_crid"
            ),
            CheckConstraint(
                condition=Q(madurez__in=Madurez.values),
                name="chk_%(class)s_madurez",
            ),
            CheckConstraint(
                condition=Q(orbita__in=Orbita.values),
                name="chk_%(class)s_orbita",
            ),
            CheckConstraint(
                condition=Q(fin_at__gt=F("inicio_at")),
                name="chk_%(class)s_tiempo",
            ),
            UniqueConstraint(fields=["granulo"], name="unq_%(class)s_granulo"),
        )

        indexes: Sequence[Index] = (
            *ApiAppendOnlyModel.Meta.indexes,
            Index(
                fields=["track", "frame", "orbita", "inicio_at"],
                name="idx_%(class)s_pasada",
            ),
        )

        ordering: Sequence[str] = ("inicio_at", "granulo")


########################################################################################


@track_table()
class Recorte(ApiProtectedModel):
    producto = ForeignKey(on_delete=RESTRICT, related_name="recortes", to=Producto)
    region = ForeignKey(on_delete=RESTRICT, related_name="recortes", to=Region)

    estado = CharField(
        choices=EstadoRecorte.choices,
        db_default=EstadoRecorte.PENDIENTE,
        default=EstadoRecorte.PENDIENTE,
        max_length=12,
    )
    intentos = SmallIntegerField(db_default=0, default=0)
    error = TextField(db_default="", default="")
    motivo_descarte = TextField(db_default="", default="")

    archivo = CharField(db_default="", default="", max_length=255)
    sha256 = CharField(db_default="", default="", max_length=64)
    bytes = BigIntegerField(null=True)
    ventana = ArrayField(IntegerField(), db_default=[], default=list, size=4)
    pixel_m = FloatField(null=True)
    epsg_nativo = IntegerField(null=True)
    incidencia = FloatField(null=True)
    mascara_modo = CharField(db_default="estricta", default="estricta", max_length=10)
    recortado_at = DateTimeField(null=True)

    class Meta(ApiProtectedModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(estado__in=EstadoRecorte.values),
                name="chk_%(class)s_estado",
            ),
            CheckConstraint(
                condition=(
                    Q(estado=EstadoRecorte.RECORTADO)
                    & ~Q(archivo="")
                    & Q(recortado_at__isnull=False)
                    & ~Q(sha256="")
                    & Q(ventana__len=4)
                )
                | (~Q(estado=EstadoRecorte.RECORTADO)),
                name="chk_%(class)s_recortado_completo",
            ),
            CheckConstraint(
                condition=Q(estado=EstadoRecorte.DESCARTADO, motivo_descarte__gt="")
                | (~Q(estado=EstadoRecorte.DESCARTADO) & Q(motivo_descarte="")),
                name="chk_%(class)s_descarte_motivo",
            ),
            CheckConstraint(
                condition=Q(intentos__range=(0, INTENTOS_MAXIMOS)),
                name="chk_%(class)s_intentos",
            ),
            CheckConstraint(
                condition=Q(sha256="") | Q(sha256__regex=PATRON_SHA256),
                name="chk_%(class)s_sha256",
            ),
            UniqueConstraint(
                fields=["producto", "region"],
                name="unq_%(class)s_producto_region",
            ),
        )

        indexes: Sequence[Index] = (
            *ApiProtectedModel.Meta.indexes,
            Index(
                condition=(
                    Q(estado__in=[EstadoRecorte.PENDIENTE, EstadoRecorte.FALLIDO])
                    & Q(intentos__lt=INTENTOS_MAXIMOS)
                ),
                fields=["region"],
                name="idx_%(class)s_pendientes",
            ),
        )

        triggers: Sequence[TriggerType] = (
            *ApiProtectedModel.Meta.triggers,
            ReadOnly(fields=["producto", "region"], name="trg_readonly_productoregion"),
            Protect(
                condition=(
                    TriggerQ(
                        old__estado__in=[
                            EstadoRecorte.RECORTADO,
                            EstadoRecorte.DESCARTADO,
                        ]
                    )
                    & TriggerQ(new__estado__df=TriggerF("old__estado"))
                ),
                name="trg_recorte_transicion_valida",
                operation=Update,
            ),
        )


########################################################################################


@track_table()
class Adquisicion(ApiProtectedModel):
    region = ForeignKey(on_delete=RESTRICT, related_name="adquisiciones", to=Region)

    track = SmallIntegerField()
    orbita = CharField(choices=Orbita.choices, max_length=4)
    frames = ArrayField(SmallIntegerField())
    inicio_at = DateTimeField()
    pasada_at = DateTimeField(db_default=None, default=None, null=True)
    fecha_codigo = CharField(db_default="", default="", max_length=20)

    madurez = CharField(choices=Madurez.choices, max_length=12)
    crid = CharField(max_length=6)

    incidencia = FloatField(null=True)
    cobertura = FloatField()

    grilla_archivo = CharField(db_default="", default="", max_length=255)
    grilla_sha256 = CharField(db_default="", default="", max_length=64)

    excluida = BooleanField(db_default=False, default=False)
    motivo_exclusion = TextField(db_default="", default="")

    reemplazada = BooleanField(db_default=False, default=False)
    reemplaza_a = OneToOneField(
        null=True,
        on_delete=RESTRICT,
        related_name="reemplazo",
        to="self",
    )

    class Meta(ApiProtectedModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(cobertura__range=(0, 1)),
                name="chk_%(class)s_cobertura",
            ),
            CheckConstraint(
                condition=Q(excluida=True, motivo_exclusion__gt="")
                | Q(excluida=False, motivo_exclusion=""),
                name="chk_%(class)s_exclusion_motivo",
            ),
            CheckConstraint(
                condition=(Q(grilla_archivo="") & Q(grilla_sha256=""))
                | (~Q(grilla_archivo="") & Q(grilla_sha256__regex=PATRON_SHA256)),
                name="chk_%(class)s_grilla_completa",
            ),
            CheckConstraint(
                condition=~Q(reemplaza_a=F("id")),
                name="chk_%(class)s_no_se_reemplaza_a_si_misma",
            ),
            CheckConstraint(
                condition=Q(crid__regex=PATRON_CRID), name="chk_%(class)s_crid"
            ),
            UniqueConstraint(
                condition=Q(reemplazada=False),
                fields=["region", "track", "orbita", "pasada_at"],
                name="unq_%(class)s_pasada_vigente",
            ),
            UniqueConstraint(
                condition=Q(reemplazada=False),
                fields=["region", "fecha_codigo"],
                name="unq_%(class)s_region_fecha",
            ),
        )

        indexes: Sequence[Index] = (
            *ApiProtectedModel.Meta.indexes,
            Index(
                condition=Q(reemplazada=False, excluida=False),
                fields=["region", "madurez", "inicio_at"],
                name="idx_%(class)s_vigentes",
            ),
        )

        ordering: Sequence[str] = ("inicio_at", "track")

        triggers: Sequence[TriggerType] = (
            *ApiProtectedModel.Meta.triggers,
            Trigger(
                name="trg_adquisicion_derivar_codigo",
                operation=Insert,
                when=Before,
                func="""
                NEW.pasada_at := date_trunc('minute', NEW.inicio_at AT TIME ZONE 'UTC')
                    AT TIME ZONE 'UTC';
                NEW.fecha_codigo := to_char(
                    NEW.inicio_at AT TIME ZONE 'UTC', 'YYYY-MM-DD'
                )
                    || '_' || lpad(NEW.track::text, 3, '0') || '_' || NEW.orbita;
                RETURN NEW;
                """,
            ),
            ReadOnly(
                fields=[
                    "region",
                    "track",
                    "orbita",
                    "inicio_at",
                    "pasada_at",
                    "fecha_codigo",
                    "madurez",
                    "crid",
                    "frames",
                    "reemplaza_a",
                ],
                name="trg_readonly_adquisicion",
            ),
            Trigger(
                name="trg_adquisicion_aplicar_reemplazo",
                operation=Insert,
                when=Before,
                declare=[("anterior", "RECORD")],
                func="""
                IF NEW.reemplaza_a_id IS NULL THEN
                    RETURN NEW;
                END IF;

                SELECT region_id, track, orbita, inicio_at, crid, reemplazada
                INTO anterior FROM mangrooveadquisiciones_adquisicion
                WHERE id = NEW.reemplaza_a_id FOR UPDATE;

                IF anterior.region_id <> NEW.region_id
                    OR anterior.track <> NEW.track
                    OR anterior.orbita <> NEW.orbita
                    OR date_trunc('minute', anterior.inicio_at)
                        <> date_trunc('minute', NEW.inicio_at)
                THEN
                    RAISE EXCEPTION 'El reemplazo no es de la misma pasada.'
                        USING ERRCODE = 'check_violation';
                END IF;

                IF NEW.crid <= anterior.crid THEN
                    RAISE EXCEPTION 'El reemplazo necesita un CRID mayor que %.',
                        anterior.crid
                        USING ERRCODE = 'check_violation';
                END IF;

                IF anterior.reemplazada THEN
                    RAISE EXCEPTION 'La adquisición anterior ya fue reemplazada.'
                        USING ERRCODE = 'check_violation';
                END IF;

                PERFORM set_config('mangroove.reemplazando', 'on', true);

                UPDATE mangrooveadquisiciones_adquisicion
                SET reemplazada = TRUE WHERE id = NEW.reemplaza_a_id;

                PERFORM set_config('mangroove.reemplazando', 'off', true);

                RETURN NEW;
                """,
            ),
            Trigger(
                condition=TriggerQ(new__reemplazada__df=TriggerF("old__reemplazada")),
                name="trg_readonly_reemplazo",
                operation=Update,
                when=Before,
                func="""
                IF OLD.reemplazada OR coalesce(
                    current_setting('mangroove.reemplazando', true), 'off'
                ) <> 'on' THEN
                    RAISE EXCEPTION 'Solo un reproceso reemplaza una adquisición.'
                        USING ERRCODE = 'check_violation';
                END IF;

                RETURN NEW;
                """,
            ),
        )


########################################################################################


class AdquisicionRecorte(ApiAppendOnlyModel):
    adquisicion = ForeignKey(on_delete=RESTRICT, related_name="+", to=Adquisicion)
    recorte = OneToOneField(on_delete=RESTRICT, related_name="+", to=Recorte)

    class Meta(ApiAppendOnlyModel.Meta):  # ty: ignore[invalid-attribute-override]
        triggers: Sequence[TriggerType] = (
            *ApiAppendOnlyModel.Meta.triggers,
            Trigger(
                name="trg_adquisicionrecorte_coherente",
                operation=Insert,
                when=Before,
                declare=[("a", "RECORD"), ("r", "RECORD")],
                func="""
                SELECT region_id, track, orbita, crid, inicio_at INTO a
                FROM mangrooveadquisiciones_adquisicion WHERE id = NEW.adquisicion_id;

                SELECT rc.region_id, rc.estado, p.track, p.orbita, p.crid, p.inicio_at
                INTO r
                FROM mangrooveadquisiciones_recorte rc
                JOIN mangrooveadquisiciones_producto p ON p.id = rc.producto_id
                WHERE rc.id = NEW.recorte_id;

                IF r.estado <> 'recortado' OR r.region_id <> a.region_id
                    OR r.track <> a.track OR r.orbita <> a.orbita OR r.crid <> a.crid
                    OR abs(extract(epoch FROM (r.inicio_at - a.inicio_at))) >= 120
                THEN
                    RAISE EXCEPTION 'El recorte no pertenece a esta pasada.'
                        USING ERRCODE = 'check_violation';
                END IF;

                RETURN NEW;
                """,
            ),
        )


########################################################################################


@track_table()
class Brecha(ApiProtectedModel):
    rango = DateTimeRangeField()
    motivo = TextField()
    fuente_url = TextField(db_default="", default="")

    class Meta(ApiProtectedModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            ExclusionConstraint(
                expressions=[("rango", RangeOperators.OVERLAPS)],
                name="excl_%(class)s_rango",
            ),
        )

        ordering: Sequence[str] = ("rango",)


########################################################################################


@track_table()
class Sincronizacion(ApiProtectedModel):
    region = ForeignKey(on_delete=RESTRICT, related_name="sincronizaciones", to=Region)
    origen = CharField(choices=OrigenSincronizacion.choices, max_length=10)
    solicitada_por = ForeignKey(
        null=True, on_delete=RESTRICT, related_name="+", to=ApiUser
    )

    estado = CharField(
        choices=EstadoSincronizacion.choices,
        db_default=EstadoSincronizacion.EN_CURSO,
        default=EstadoSincronizacion.EN_CURSO,
        max_length=12,
    )
    inicio_at = DateTimeField(db_default=Now(), default=now)
    fin_at = DateTimeField(null=True)

    n_encontrados = IntegerField(db_default=0, default=0)
    n_recortados = IntegerField(db_default=0, default=0)
    n_descartados = IntegerField(db_default=0, default=0)
    n_fallidos = IntegerField(db_default=0, default=0)
    bytes_transferidos = BigIntegerField(db_default=0, default=0)
    error = TextField(db_default="", default="")

    class Meta(ApiProtectedModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(
                    origen=OrigenSincronizacion.MANUAL, solicitada_por__isnull=False
                )
                | Q(
                    origen=OrigenSincronizacion.PROGRAMADA, solicitada_por__isnull=True
                ),
                name="chk_%(class)s_origen",
            ),
            CheckConstraint(
                condition=Q(estado=EstadoSincronizacion.EN_CURSO, fin_at__isnull=True)
                | (~Q(estado=EstadoSincronizacion.EN_CURSO) & Q(fin_at__isnull=False)),
                name="chk_%(class)s_cierre",
            ),
            UniqueConstraint(
                condition=Q(estado=EstadoSincronizacion.EN_CURSO),
                fields=["region"],
                name="unq_%(class)s_region_en_curso",
            ),
        )

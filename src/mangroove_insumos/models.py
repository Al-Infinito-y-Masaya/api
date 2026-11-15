from typing import TYPE_CHECKING

from django.db.models import (
    RESTRICT,
    CharField,
    CheckConstraint,
    DateField,
    FloatField,
    ForeignKey,
    JSONField,
    Q,
    SmallIntegerField,
    TextField,
    UniqueConstraint,
)
from pgtrigger import Before, Insert, Trigger

from api_auth.models import ApiUser
from api_core.models.base import ApiAppendOnlyModel
from api_media.models import ApiMedia
from mangroove_adquisiciones.models import Adquisicion
from mangroove_insumos.enums import FormatoInsumo, TipoInsumo, TipoSerie
from mangroove_regiones.models import Region

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import BaseConstraint
    from pgtrigger import Trigger as TriggerType

########################################################################################

PATRON_SHA256: str = r"^[0-9a-f]{64}$"

ESCENAS: tuple[str, ...] = (TipoInsumo.OPTICO, TipoInsumo.BANDA_C)

########################################################################################


class Insumo(ApiAppendOnlyModel):
    region = ForeignKey(on_delete=RESTRICT, related_name="insumos", to=Region)
    tipo = CharField(choices=TipoInsumo.choices, max_length=20)
    version = SmallIntegerField(db_default=0, default=0)
    formato = CharField(choices=FormatoInsumo.choices, max_length=8)

    media = ForeignKey(on_delete=RESTRICT, related_name="+", to=ApiMedia)
    sha256 = CharField(max_length=64)
    grilla_archivo = CharField(db_default="", default="", max_length=255)
    grilla_sha256 = CharField(db_default="", default="", max_length=64)

    fuente = TextField()
    fuente_url = TextField(db_default="", default="")
    licencia = CharField(max_length=50)
    fecha_dato = DateField(null=True)
    nubes_pct = FloatField(null=True)

    cargado_por = ForeignKey(on_delete=RESTRICT, related_name="+", to=ApiUser)

    class Meta(ApiAppendOnlyModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(tipo__in=TipoInsumo.values),
                name="chk_%(class)s_tipo",
            ),
            CheckConstraint(
                condition=Q(formato__in=FormatoInsumo.values),
                name="chk_%(class)s_formato",
            ),
            CheckConstraint(
                condition=Q(tipo__in=ESCENAS, fecha_dato__isnull=False)
                | (~Q(tipo__in=ESCENAS) & Q(fecha_dato__isnull=True)),
                name="chk_%(class)s_escena",
            ),
            CheckConstraint(
                condition=Q(nubes_pct__isnull=True)
                | Q(tipo=TipoInsumo.OPTICO, nubes_pct__range=(0, 100)),
                name="chk_%(class)s_nubes",
            ),
            CheckConstraint(
                condition=Q(sha256__regex=PATRON_SHA256),
                name="chk_%(class)s_sha256",
            ),
            CheckConstraint(
                condition=Q(grilla_sha256="") | Q(grilla_sha256__regex=PATRON_SHA256),
                name="chk_%(class)s_grillasha256",
            ),
            UniqueConstraint(
                fields=["region", "tipo", "version"],
                name="unq_%(class)s_region_tipo_version",
            ),
            UniqueConstraint(
                fields=["region", "tipo", "sha256"],
                name="unq_%(class)s_region_tipo_sha256",
            ),
        )

        ordering: Sequence[str] = ("region", "tipo", "version")

        triggers: Sequence[TriggerType] = (
            *ApiAppendOnlyModel.Meta.triggers,
            Trigger(
                name="trg_insumo_derivar_version",
                operation=Insert,
                when=Before,
                func="""
                PERFORM pg_advisory_xact_lock(
                    hashtext('insumo:' || NEW.region_id::text)
                );

                SELECT coalesce(max(version), 0) + 1 INTO NEW.version
                FROM mangrooveinsumos_insumo
                WHERE region_id = NEW.region_id AND tipo = NEW.tipo;

                RETURN NEW;
                """,
            ),
        )


########################################################################################


class Estanque(ApiAppendOnlyModel):
    insumo = ForeignKey(on_delete=RESTRICT, related_name="estanques", to=Insumo)
    numero = SmallIntegerField()
    codigo = CharField(max_length=30)
    geometria = JSONField()
    area_ha = FloatField()

    class Meta(ApiAppendOnlyModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(condition=Q(numero__gt=0), name="chk_%(class)s_numero"),
            CheckConstraint(condition=Q(area_ha__gt=0), name="chk_%(class)s_area"),
            UniqueConstraint(
                fields=["insumo", "codigo"], name="unq_%(class)s_insumo_codigo"
            ),
            UniqueConstraint(
                fields=["insumo", "numero"], name="unq_%(class)s_insumo_numero"
            ),
        )

        ordering: Sequence[str] = ("insumo", "numero")

        triggers: Sequence[TriggerType] = (
            *ApiAppendOnlyModel.Meta.triggers,
            Trigger(
                name="trg_estanque_insumo_tipo",
                operation=Insert,
                when=Before,
                func="""
                IF (SELECT tipo FROM mangrooveinsumos_insumo WHERE id = NEW.insumo_id)
                    <> 'estanques'
                THEN
                    RAISE EXCEPTION 'El insumo de un estanque debe ser de estanques.'
                        USING ERRCODE = 'check_violation';
                END IF;

                RETURN NEW;
                """,
            ),
        )


########################################################################################


class SerieCargada(ApiAppendOnlyModel):
    region = ForeignKey(on_delete=RESTRICT, related_name="series", to=Region)
    tipo = CharField(choices=TipoSerie.choices, max_length=6)
    media = ForeignKey(on_delete=RESTRICT, related_name="+", to=ApiMedia)
    sha256 = CharField(max_length=64)
    fuente = TextField()
    cargada_por = ForeignKey(on_delete=RESTRICT, related_name="+", to=ApiUser)

    class Meta(ApiAppendOnlyModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(tipo__in=TipoSerie.values), name="chk_%(class)s_tipo"
            ),
            CheckConstraint(
                condition=Q(sha256__regex=PATRON_SHA256),
                name="chk_%(class)s_sha256",
            ),
        )


########################################################################################


class EstimacionMarea(ApiAppendOnlyModel):
    adquisicion = ForeignKey(on_delete=RESTRICT, related_name="mareas", to=Adquisicion)
    modelo = CharField(max_length=50)
    serie = ForeignKey(null=True, on_delete=RESTRICT, related_name="+", to=SerieCargada)
    altura_m = FloatField()

    class Meta(ApiAppendOnlyModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(altura_m__range=(-10, 10)),
                name="chk_%(class)s_altura",
            ),
            CheckConstraint(
                condition=Q(serie__isnull=True) & ~Q(modelo__startswith="serie:")
                | Q(serie__isnull=False, modelo__startswith="serie:"),
                name="chk_%(class)s_serie",
            ),
            UniqueConstraint(
                fields=["adquisicion", "modelo"],
                name="unq_%(class)s_adquisicion_modelo",
            ),
        )


########################################################################################


class LluviaDiaria(ApiAppendOnlyModel):
    region = ForeignKey(on_delete=RESTRICT, related_name="lluvias", to=Region)
    fecha = DateField()
    fuente = CharField(max_length=50)
    serie = ForeignKey(null=True, on_delete=RESTRICT, related_name="+", to=SerieCargada)
    mm = FloatField()

    class Meta(ApiAppendOnlyModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(mm__gte=0, mm__lt=2000), name="chk_%(class)s_mm"
            ),
            UniqueConstraint(
                fields=["region", "fecha", "fuente"],
                name="unq_%(class)s_region_fecha_fuente",
            ),
        )

        ordering: Sequence[str] = ("region", "fecha")

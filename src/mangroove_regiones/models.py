from typing import TYPE_CHECKING

from django.db.models import (
    RESTRICT,
    CharField,
    CheckConstraint,
    F,
    FloatField,
    ForeignKey,
    GeneratedField,
    Index,
    IntegerField,
    PositiveSmallIntegerField,
    Q,
    SmallIntegerField,
    TextField,
    UniqueConstraint,
    Value,
)
from pgtrigger import Before, Insert, ReadOnly, Trigger

from api_core.models.base import (
    ApiAppendOnlyModel,
    ApiSoftDeleteModel,
    remove_default_touch,
    touch_updatedat_trigger,
)
from api_utils.db import track_table
from mangroove_motor.grilla import Grilla

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pgtrigger import Trigger as TriggerType

########################################################################################

CELDAS_MAXIMAS: int = 1_000_000

CAMPOS_GRILLA: tuple[str, ...] = (
    "codigo",
    "epsg",
    "celda_m",
    "x0",
    "y0",
    "ancho",
    "alto",
)

########################################################################################


@track_table()
class Region(ApiSoftDeleteModel):
    codigo = CharField(max_length=50)
    nombre = CharField(max_length=150)
    aoi_wkt = TextField()

    lon_min = FloatField()
    lat_min = FloatField()
    lon_max = FloatField()
    lat_max = FloatField()

    centro_lon = FloatField()
    centro_lat = FloatField()
    zoom_inicial = PositiveSmallIntegerField(db_default=11, default=11)
    zona_horaria = CharField(
        db_default="America/Managua", default="America/Managua", max_length=50
    )

    epsg = IntegerField()
    celda_m = SmallIntegerField(db_default=100, default=100)
    x0 = FloatField()
    y0 = FloatField()
    ancho = IntegerField()
    alto = IntegerField()
    n_celdas = GeneratedField(
        db_persist=True,
        expression=F("ancho") * F("alto"),
        output_field=IntegerField(),
    )
    margen_m = IntegerField(db_default=2000, default=2000)

    marea_lon = FloatField()
    marea_lat = FloatField()

    class Meta(ApiSoftDeleteModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[CheckConstraint | UniqueConstraint] = (
            CheckConstraint(
                condition=Q(codigo__regex=r"^[a-z][a-z0-9_]*$"),
                name="chk_%(class)s_codigo",
            ),
            CheckConstraint(
                condition=(
                    Q(
                        lon_min__gte=-180,
                        lon_max__lte=180,
                        lat_min__gte=-90,
                        lat_max__lte=90,
                    )
                    & Q(lon_min__lt=F("lon_max"), lat_min__lt=F("lat_max"))
                ),
                name="chk_%(class)s_caja",
            ),
            CheckConstraint(
                condition=Q(epsg__range=(32601, 32660)) | Q(epsg__range=(32701, 32760)),
                name="chk_%(class)s_epsg_utm",
            ),
            CheckConstraint(
                condition=Q(celda_m__range=(10, 1000)),
                name="chk_%(class)s_celda",
            ),
            CheckConstraint(
                condition=Q(ancho__gt=0, alto__gt=0)
                & Q(ancho__lte=Value(CELDAS_MAXIMAS) / F("alto")),
                name="chk_%(class)s_tamano",
            ),
            CheckConstraint(
                condition=Q(zoom_inicial__range=(0, 22)),
                name="chk_%(class)s_zoom",
            ),
            CheckConstraint(
                condition=Q(margen_m__gte=0),
                name="chk_%(class)s_margen",
            ),
            UniqueConstraint(fields=["codigo"], name="unq_%(class)s_codigo"),
        )

        triggers: Sequence[TriggerType] = (
            *remove_default_touch(ApiSoftDeleteModel.Meta.triggers),
            touch_updatedat_trigger(exclude_generated=["n_celdas"]),
            ReadOnly(fields=list(CAMPOS_GRILLA), name="trg_readonly_grilla"),
        )

    def grilla(self) -> Grilla:
        return Grilla(
            epsg=self.epsg,  # ty: ignore[invalid-argument-type]
            x0=self.x0,  # ty: ignore[invalid-argument-type]
            y0=self.y0,  # ty: ignore[invalid-argument-type]
            celda_m=float(self.celda_m),  # ty: ignore[invalid-argument-type]
            ancho=self.ancho,  # ty: ignore[invalid-argument-type]
            alto=self.alto,  # ty: ignore[invalid-argument-type]
        )


########################################################################################


class Celda(ApiAppendOnlyModel):
    region = ForeignKey(on_delete=RESTRICT, related_name="celdas", to=Region)

    fila = IntegerField()
    columna = IntegerField()

    este_m = IntegerField(db_default=0, default=0)
    norte_m = IntegerField(db_default=0, default=0)
    codigo = CharField(db_default="", default="", max_length=24)

    lon = FloatField()
    lat = FloatField()

    class Meta(ApiAppendOnlyModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[CheckConstraint | UniqueConstraint] = (
            CheckConstraint(
                condition=Q(fila__gte=0, columna__gte=0),
                name="chk_%(class)s_indices",
            ),
            UniqueConstraint(
                fields=["region", "fila", "columna"],
                name="unq_%(class)s_region_fila_columna",
            ),
            UniqueConstraint(
                fields=["region", "codigo"], name="unq_%(class)s_region_codigo"
            ),
        )

        indexes: Sequence[Index] = ()

        ordering: Sequence[str] = ("region", "fila", "columna")

        triggers: Sequence[TriggerType] = (
            *ApiAppendOnlyModel.Meta.triggers,
            Trigger(
                name="trg_celda_derivar_centro",
                operation=Insert,
                when=Before,
                declare=[("g", "RECORD")],
                func="""
                SELECT x0, y0, celda_m, ancho, alto INTO g
                FROM mangrooveregiones_region WHERE id = NEW.region_id;

                IF NEW.fila >= g.alto OR NEW.columna >= g.ancho THEN
                    RAISE EXCEPTION 'La celda (%, %) está fuera de la grilla.',
                        NEW.fila, NEW.columna
                        USING ERRCODE = 'check_violation';
                END IF;

                NEW.este_m := round(g.x0 + (NEW.columna + 0.5) * g.celda_m);
                NEW.norte_m := round(g.y0 - (NEW.fila + 0.5) * g.celda_m);
                NEW.codigo := 'c_' || NEW.este_m || '_' || NEW.norte_m;

                RETURN NEW;
                """,
            ),
        )

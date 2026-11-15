from dataclasses import fields
from typing import TYPE_CHECKING, Final

from django.contrib.postgres.fields import ArrayField
from django.db.models import (
    CASCADE,
    RESTRICT,
    BooleanField,
    CharField,
    CheckConstraint,
    DateField,
    DateTimeField,
    F,
    FloatField,
    ForeignKey,
    GeneratedField,
    Index,
    IntegerField,
    Q,
    SmallIntegerField,
    TextField,
    UUIDField,
    UniqueConstraint,
)
from django.db.models.functions import Now
from django.utils.timezone import now
from pgtrigger import (
    After,
    Before,
    Delete,
    F as TriggerF,
    Insert,
    Q as TriggerQ,
    ReadOnly,
    Trigger,
    Update,
)

from api_auth.models import ApiUser
from api_core.models.base import ApiAppendOnlyModel, ApiModel, ApiProtectedModel
from api_utils.db import track_table
from mangroove_adquisiciones.models import Adquisicion
from mangroove_analisis.enums import (
    EstadoCorrida,
    MadurezCorrida,
    NivelMareaCorrida,
    OrbitaCorrida,
    PruebaEstadistica,
)
from mangroove_insumos.models import Estanque, Insumo
from mangroove_motor.perfil import Banda, Clase, Perfil
from mangroove_regiones.models import Celda, Region

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import BaseConstraint
    from pgtrigger import Trigger as TriggerType

########################################################################################

PATRON_SEMVER: str = r"^\d+\.\d+\.\d+$"

PATRON_SHA256: str = r"^[0-9a-f]{64}$"

CLASES_VALIDAS: Final[list[int]] = [int(c) for c in Clase]

########################################################################################


def resultado_solo_insercion() -> Trigger:
    return Trigger(
        name="trg_resultado_solo_insercion",
        operation=Update | Delete,
        when=Before,
        func="""
        IF TG_OP = 'UPDATE' THEN
            RAISE EXCEPTION 'Los resultados de una corrida no se editan.'
                USING ERRCODE = 'check_violation';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM mangrooveanalisis_corrida c
            WHERE c.id = OLD.corrida_id
              AND c.estado = 'retirada'
              AND c.purgar_despues_de <= now()
        ) THEN
            RAISE EXCEPTION 'Solo la purga de una corrida retirada borra resultados.'
                USING ERRCODE = 'check_violation';
        END IF;

        RETURN OLD;
        """,
    )


class ResultadoCorridaModel(ApiModel):
    created_at = DateTimeField(db_default=Now(), default=now)

    class Meta(ApiModel.Meta):  # ty: ignore[invalid-attribute-override]
        abstract: bool = True

        triggers: Sequence[TriggerType] = (
            *ApiModel.Meta.triggers,
            resultado_solo_insercion(),
        )


########################################################################################


class PerfilUmbrales(ApiAppendOnlyModel):
    codigo = CharField(max_length=50)
    version = SmallIntegerField(db_default=0, default=0)
    nombre = CharField(max_length=100)

    ow_hh_db = FloatField()
    ow_hv_db = FloatField()
    iv_hh_db = FloatField()
    iv_ratio_db = FloatField()
    iv_ratio_holgura_db = FloatField()
    cambio_hh_db = FloatField()
    cambio_hv_db = FloatField()
    nc_hh_db = FloatField()
    nc_hv_db = FloatField()
    usar_coherencia = BooleanField()
    coherencia_min = FloatField()
    marea_alta_m = FloatField()
    marea_baja_m = FloatField()
    lluvia_max_mm = FloatField()
    if_alta_desconectada = FloatField()
    min_fechas_alta = SmallIntegerField()
    mayoria = BooleanField()
    usar_elevacion = BooleanField()
    if_esperada_min = FloatField()
    marea_margen_m = FloatField()
    humedal_pendiente_max = FloatField()
    humedal_cota_max = FloatField()
    estables_minimas = IntegerField()
    sigma_db = FloatField()
    cusum_b = SmallIntegerField()
    cusum_confianza = FloatField()
    cusum_perdida_db = FloatField()
    cv_estanque = FloatField()
    cv_banda = CharField(choices=[(b.value, b.value) for b in Banda], max_length=2)
    puntaje_distancia = FloatField()
    puntaje_area = FloatField()
    puntaje_inundacion = FloatField()

    creado_por = ForeignKey(null=True, on_delete=RESTRICT, related_name="+", to=ApiUser)

    class Meta(ApiAppendOnlyModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(codigo__regex=r"^[a-z][a-z0-9_]*$"),
                name="chk_%(class)s_codigo",
            ),
            CheckConstraint(
                condition=Q(marea_baja_m__lt=F("marea_alta_m")),
                name="chk_%(class)s_mareas",
            ),
            CheckConstraint(
                condition=Q(
                    coherencia_min__range=(0, 1),
                    if_alta_desconectada__range=(0, 1),
                    if_esperada_min__range=(0, 1),
                    cusum_confianza__range=(0, 1),
                ),
                name="chk_%(class)s_fracciones",
            ),
            CheckConstraint(
                condition=Q(cusum_b__range=(20, 1000), cusum_perdida_db__gt=0),
                name="chk_%(class)s_cusum",
            ),
            CheckConstraint(
                condition=Q(
                    ow_hh_db__lt=F("iv_hh_db"), sigma_db__gt=0, min_fechas_alta__gte=1
                ),
                name="chk_%(class)s_clases",
            ),
            CheckConstraint(
                condition=Q(cv_banda__in=[b.value for b in Banda]),
                name="chk_%(class)s_cvbanda",
            ),
            UniqueConstraint(
                fields=["codigo", "version"], name="unq_%(class)s_codigo_version"
            ),
        )

        ordering: Sequence[str] = ("codigo", "-version")

        triggers: Sequence[TriggerType] = (
            *ApiAppendOnlyModel.Meta.triggers,
            Trigger(
                name="trg_perfilumbrales_derivar_version",
                operation=Insert,
                when=Before,
                func="""
                PERFORM pg_advisory_xact_lock(hashtext('perfil:' || NEW.codigo));

                SELECT coalesce(max(version), 0) + 1 INTO NEW.version
                FROM mangrooveanalisis_perfilumbrales WHERE codigo = NEW.codigo;

                RETURN NEW;
                """,
            ),
        )

    def a_perfil(self) -> Perfil:
        valores: dict = {f.name: getattr(self, f.name) for f in fields(Perfil)}

        return Perfil(**(valores | {"cv_banda": Banda(self.cv_banda)}))  # ty: ignore[invalid-argument-type]


########################################################################################


@track_table()
class Corrida(ApiProtectedModel):
    region = ForeignKey(on_delete=RESTRICT, related_name="corridas", to=Region)
    version = CharField(max_length=20)
    perfil = ForeignKey(on_delete=RESTRICT, related_name="corridas", to=PerfilUmbrales)
    madurez = CharField(choices=MadurezCorrida.choices, max_length=12)
    modelo_marea = CharField(max_length=50)
    fuente_lluvia = CharField(db_default="", default="", max_length=50)
    orbita = CharField(
        choices=OrbitaCorrida.choices,
        db_default=OrbitaCorrida.AMBAS,
        default=OrbitaCorrida.AMBAS,
        max_length=5,
    )
    tracks = ArrayField(SmallIntegerField(), db_default=[], default=list)
    fijadas = ArrayField(UUIDField(), db_default=[], default=list)
    desde = DateField(null=True)
    hasta = DateField(null=True)
    codigo_version = CharField(max_length=40)
    semilla = IntegerField(db_default=12345, default=12345)

    estado = CharField(
        choices=EstadoCorrida.choices,
        db_default=EstadoCorrida.PENDIENTE,
        default=EstadoCorrida.PENDIENTE,
        max_length=12,
    )
    vigente = BooleanField(db_default=False, default=False)
    n_fechas = SmallIntegerField()

    solicitada_por = ForeignKey(
        null=True, on_delete=RESTRICT, related_name="+", to=ApiUser
    )
    publicada_por = ForeignKey(
        null=True, on_delete=RESTRICT, related_name="+", to=ApiUser
    )

    iniciada_at = DateTimeField(null=True)
    terminada_at = DateTimeField(null=True)
    publicada_at = DateTimeField(null=True)
    retirada_at = DateTimeField(null=True)
    motivo_retiro = TextField(db_default="", default="")
    purgar_despues_de = DateTimeField(null=True)
    error = TextField(db_default="", default="")

    cubo_archivo = CharField(db_default="", default="", max_length=255)
    cubo_sha256 = CharField(db_default="", default="", max_length=64)

    class Meta(ApiProtectedModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(version__regex=PATRON_SEMVER), name="chk_%(class)s_version"
            ),
            CheckConstraint(
                condition=Q(estado__in=EstadoCorrida.values),
                name="chk_%(class)s_estado",
            ),
            CheckConstraint(
                condition=Q(madurez__in=MadurezCorrida.values),
                name="chk_%(class)s_madurez",
            ),
            CheckConstraint(
                condition=Q(vigente=False) | Q(estado=EstadoCorrida.PUBLICADA),
                name="chk_%(class)s_vigente_publicada",
            ),
            CheckConstraint(
                condition=(
                    Q(estado__in=[EstadoCorrida.PUBLICADA, EstadoCorrida.RETIRADA])
                    & Q(publicada_at__isnull=False, publicada_por__isnull=False)
                )
                | (
                    ~Q(estado__in=[EstadoCorrida.PUBLICADA, EstadoCorrida.RETIRADA])
                    & Q(publicada_at__isnull=True)
                ),
                name="chk_%(class)s_publicacion",
            ),
            CheckConstraint(
                condition=(
                    Q(estado=EstadoCorrida.RETIRADA)
                    & Q(retirada_at__isnull=False, purgar_despues_de__isnull=False)
                    & ~Q(motivo_retiro="")
                )
                | (~Q(estado=EstadoCorrida.RETIRADA) & Q(retirada_at__isnull=True)),
                name="chk_%(class)s_retiro",
            ),
            CheckConstraint(
                condition=Q(estado=EstadoCorrida.FALLIDA, error__gt="")
                | (~Q(estado=EstadoCorrida.FALLIDA) & Q(error="")),
                name="chk_%(class)s_falla",
            ),
            CheckConstraint(
                condition=Q(cubo_sha256="") | Q(cubo_sha256__regex=PATRON_SHA256),
                name="chk_%(class)s_cubo",
            ),
            CheckConstraint(
                condition=Q(n_fechas__gte=1, fijadas__len=F("n_fechas")),
                name="chk_%(class)s_nfechas",
            ),
            UniqueConstraint(
                fields=["region", "version"], name="unq_%(class)s_region_version"
            ),
            UniqueConstraint(
                condition=Q(vigente=True),
                fields=["region"],
                name="unq_%(class)s_region_vigente",
            ),
        )

        indexes: Sequence[Index] = (
            *ApiProtectedModel.Meta.indexes,
            Index(
                condition=Q(estado=EstadoCorrida.PENDIENTE),
                fields=["created_at"],
                name="idx_%(class)s_cola",
            ),
            Index(
                condition=Q(estado=EstadoCorrida.RETIRADA),
                fields=["purgar_despues_de"],
                name="idx_%(class)s_purga",
            ),
        )

        triggers: Sequence[TriggerType] = (
            *ApiProtectedModel.Meta.triggers,
            Trigger(
                condition=TriggerQ(new__estado__df=TriggerF("old__estado")),
                name="trg_corrida_transicion_valida",
                operation=Update,
                when=Before,
                func="""
                IF NOT (
                    (OLD.estado = 'pendiente' AND NEW.estado = 'en_proceso')
                    OR (
                        OLD.estado = 'en_proceso'
                        AND NEW.estado IN ('completada', 'fallida')
                    )
                    OR (OLD.estado = 'completada' AND NEW.estado = 'publicada')
                    OR (OLD.estado = 'publicada' AND NEW.estado = 'retirada')
                ) THEN
                    RAISE EXCEPTION 'Transición de corrida no permitida: % -> %.',
                        OLD.estado, NEW.estado USING ERRCODE = 'check_violation';
                END IF;

                RETURN NEW;
                """,
            ),
            ReadOnly(
                fields=[
                    "region",
                    "version",
                    "perfil",
                    "madurez",
                    "modelo_marea",
                    "fuente_lluvia",
                    "orbita",
                    "tracks",
                    "desde",
                    "hasta",
                    "semilla",
                    "n_fechas",
                    "fijadas",
                ],
                name="trg_readonly_corrida",
            ),
            Trigger(
                condition=TriggerQ(new__estado="retirada")
                & TriggerQ(old__vigente=True),
                name="trg_corrida_retiro_deja_vigente",
                operation=Update,
                when=Before,
                declare=[("relevo", "UUID")],
                func="""
                SELECT id INTO relevo FROM mangrooveanalisis_corrida
                WHERE region_id = NEW.region_id AND estado = 'publicada'
                    AND id <> NEW.id
                ORDER BY publicada_at DESC, id DESC LIMIT 1;

                IF relevo IS NULL AND (
                    SELECT is_active FROM mangrooveregiones_region
                    WHERE id = NEW.region_id
                ) THEN
                    RAISE EXCEPTION 'La región quedaría sin una corrida vigente.'
                        USING ERRCODE = 'check_violation';
                END IF;

                NEW.vigente := FALSE;

                RETURN NEW;
                """,
            ),
            Trigger(
                condition=TriggerQ(new__estado="retirada")
                & TriggerQ(old__vigente=True),
                name="trg_corrida_relevo_vigente",
                operation=Update,
                when=After,
                func="""
                UPDATE mangrooveanalisis_corrida SET vigente = TRUE
                WHERE id = (
                    SELECT id FROM mangrooveanalisis_corrida
                    WHERE region_id = NEW.region_id AND estado = 'publicada'
                    ORDER BY publicada_at DESC, id DESC LIMIT 1
                );

                RETURN NULL;
                """,
            ),
            Trigger(
                condition=TriggerQ(new__vigente=True) & TriggerQ(old__vigente=False),
                name="trg_corrida_unica_vigente",
                operation=Update,
                when=Before,
                func="""
                UPDATE mangrooveanalisis_corrida SET vigente = FALSE
                WHERE region_id = NEW.region_id AND vigente AND id <> NEW.id;

                RETURN NEW;
                """,
            ),
        )


########################################################################################


class CorridaFecha(ResultadoCorridaModel):
    corrida = ForeignKey(on_delete=CASCADE, related_name="fechas", to=Corrida)
    adquisicion = ForeignKey(on_delete=RESTRICT, related_name="+", to=Adquisicion)
    orden = SmallIntegerField()
    fecha_codigo = CharField(db_default="", default="", max_length=20)

    desfase_hh_db = FloatField()
    desfase_hv_db = FloatField()
    marea_m = FloatField(null=True)
    marea_nivel = CharField(choices=NivelMareaCorrida.choices, max_length=12)
    lluvia_3d_mm = FloatField(null=True)
    usada_en_if_alta = BooleanField()

    class Meta(ResultadoCorridaModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(
                    marea_m__isnull=True, marea_nivel=NivelMareaCorrida.DESCONOCIDA
                )
                | Q(marea_m__isnull=False)
                & ~Q(marea_nivel=NivelMareaCorrida.DESCONOCIDA),
                name="chk_%(class)s_nivel",
            ),
            CheckConstraint(
                condition=Q(usada_en_if_alta=False)
                | Q(marea_nivel=NivelMareaCorrida.ALTA),
                name="chk_%(class)s_ifalta",
            ),
            CheckConstraint(condition=Q(orden__gte=0), name="chk_%(class)s_orden"),
            UniqueConstraint(
                fields=["corrida", "orden"], name="unq_%(class)s_corrida_orden"
            ),
            UniqueConstraint(
                fields=["corrida", "adquisicion"],
                name="unq_%(class)s_corrida_adquisicion",
            ),
        )

        ordering: Sequence[str] = ("corrida", "orden")

        triggers: Sequence[TriggerType] = (
            *ResultadoCorridaModel.Meta.triggers,
            Trigger(
                name="trg_corridafecha_madurez_coherente",
                operation=Insert,
                when=Before,
                declare=[("c", "RECORD"), ("a", "RECORD")],
                func="""
                SELECT region_id, madurez INTO c
                FROM mangrooveanalisis_corrida WHERE id = NEW.corrida_id;

                SELECT region_id, madurez, reemplazada, excluida, fecha_codigo INTO a
                FROM mangrooveadquisiciones_adquisicion WHERE id = NEW.adquisicion_id;

                IF a.region_id <> c.region_id OR a.madurez <> c.madurez
                    OR a.reemplazada OR a.excluida
                THEN
                    RAISE EXCEPTION 'La adquisición no es vigente o es de otra madurez.'
                        USING ERRCODE = 'check_violation';
                END IF;

                NEW.fecha_codigo := a.fecha_codigo;

                RETURN NEW;
                """,
            ),
        )


class CorridaInsumo(ResultadoCorridaModel):
    corrida = ForeignKey(on_delete=CASCADE, related_name="insumos", to=Corrida)
    insumo = ForeignKey(on_delete=RESTRICT, related_name="+", to=Insumo)
    tipo = CharField(db_default="", default="", max_length=20)

    class Meta(ResultadoCorridaModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            UniqueConstraint(
                fields=["corrida", "insumo"], name="unq_%(class)s_corrida_insumo"
            ),
            UniqueConstraint(
                fields=["corrida", "tipo"], name="unq_%(class)s_corrida_tipo"
            ),
        )

        triggers: Sequence[TriggerType] = (
            *ResultadoCorridaModel.Meta.triggers,
            Trigger(
                name="trg_corridainsumo_coherente",
                operation=Insert,
                when=Before,
                declare=[("i", "RECORD")],
                func="""
                SELECT region_id, tipo INTO i FROM mangrooveinsumos_insumo
                WHERE id = NEW.insumo_id;

                IF i.region_id <> (
                    SELECT region_id FROM mangrooveanalisis_corrida
                    WHERE id = NEW.corrida_id
                ) THEN
                    RAISE EXCEPTION 'El insumo no es de la región de la corrida.'
                        USING ERRCODE = 'check_violation';
                END IF;

                NEW.tipo := i.tipo;

                RETURN NEW;
                """,
            ),
        )


########################################################################################


class ResultadoCelda(ResultadoCorridaModel):
    corrida = ForeignKey(on_delete=CASCADE, related_name="celdas", to=Corrida)
    celda = ForeignKey(on_delete=RESTRICT, related_name="resultados", to=Celda)

    pais = CharField(db_default="", default="", max_length=2)
    en_mascara = BooleanField()
    humedal = BooleanField()

    hh = ArrayField(SmallIntegerField())
    hv = ArrayField(SmallIntegerField())
    coherencia = ArrayField(SmallIntegerField(), db_default=[], default=list)
    clases = ArrayField(SmallIntegerField())
    clase_tipica = SmallIntegerField()

    if_total = FloatField(null=True)
    if_alta = FloatField(null=True)
    n_fechas = SmallIntegerField()
    n_fechas_alta = SmallIntegerField()
    datos_suficientes = BooleanField()
    desconectada = BooleanField()
    p_error = FloatField(null=True)
    if_esperada = FloatField(null=True)

    cambio_orden = SmallIntegerField(null=True)
    cambio_confianza = FloatField(null=True)
    cambio_delta_hv_db = FloatField(null=True)
    perdida_copa = GeneratedField(
        db_persist=True,
        expression=Q(cambio_orden__isnull=False, cambio_delta_hv_db__lt=0),
        output_field=BooleanField(),
    )

    class Meta(ResultadoCorridaModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(hh__len=F("hv__len"), hh__len__gte=1)
                & Q(clases__len=F("hh__len"))
                & (Q(coherencia__len=0) | Q(coherencia__len=F("hh__len"))),
                name="chk_%(class)s_series_alineadas",
            ),
            CheckConstraint(
                condition=Q(clases__contained_by=CLASES_VALIDAS)
                & Q(clase_tipica__in=CLASES_VALIDAS),
                name="chk_%(class)s_clases",
            ),
            CheckConstraint(
                condition=(Q(if_total__isnull=True) | Q(if_total__range=(0, 1)))
                & (Q(if_alta__isnull=True) | Q(if_alta__range=(0, 1)))
                & (Q(p_error__isnull=True) | Q(p_error__range=(0, 1)))
                & (Q(if_esperada__isnull=True) | Q(if_esperada__range=(0, 1)))
                & (
                    Q(cambio_confianza__isnull=True) | Q(cambio_confianza__range=(0, 1))
                ),
                name="chk_%(class)s_fracciones",
            ),
            CheckConstraint(
                condition=Q(en_mascara=True)
                | Q(
                    if_total__isnull=True,
                    if_alta__isnull=True,
                    p_error__isnull=True,
                    if_esperada__isnull=True,
                    cambio_orden__isnull=True,
                    desconectada=False,
                    datos_suficientes=False,
                ),
                name="chk_%(class)s_fuera_mascara",
            ),
            CheckConstraint(
                condition=Q(en_mascara=False)
                | Q(if_total__isnull=False, p_error__isnull=False),
                name="chk_%(class)s_mascara_metricas",
            ),
            CheckConstraint(
                condition=Q(datos_suficientes=True, if_alta__isnull=False)
                | Q(datos_suficientes=False, if_alta__isnull=True),
                name="chk_%(class)s_ifalta_suficiente",
            ),
            CheckConstraint(
                condition=Q(desconectada=False)
                | Q(en_mascara=True, datos_suficientes=True),
                name="chk_%(class)s_desconexion",
            ),
            CheckConstraint(
                condition=Q(
                    cambio_orden__isnull=True,
                    cambio_confianza__isnull=True,
                    cambio_delta_hv_db__isnull=True,
                )
                | Q(
                    cambio_orden__isnull=False,
                    cambio_confianza__isnull=False,
                    cambio_delta_hv_db__isnull=False,
                ),
                name="chk_%(class)s_cambio_completo",
            ),
            UniqueConstraint(
                fields=["corrida", "celda"], name="unq_%(class)s_corrida_celda"
            ),
        )

        triggers: Sequence[TriggerType] = (
            *ResultadoCorridaModel.Meta.triggers,
            Trigger(
                name="trg_resultadocelda_largo_serie",
                operation=Insert,
                when=Before,
                declare=[("c", "RECORD")],
                func="""
                SELECT region_id, n_fechas INTO c
                FROM mangrooveanalisis_corrida WHERE id = NEW.corrida_id;

                IF cardinality(NEW.hh) <> c.n_fechas OR (
                    SELECT region_id FROM mangrooveregiones_celda
                    WHERE id = NEW.celda_id
                ) <> c.region_id THEN
                    RAISE EXCEPTION 'La serie no coincide con la corrida.'
                        USING ERRCODE = 'check_violation';
                END IF;

                RETURN NEW;
                """,
            ),
        )


########################################################################################


class ResumenPais(ResultadoCorridaModel):
    corrida = ForeignKey(on_delete=CASCADE, related_name="resumen_paises", to=Corrida)
    pais = CharField(db_default="", default="", max_length=2)
    n_celdas = IntegerField()
    ha_manglar = FloatField()
    ha_desconectada = FloatField()
    ha_insuficiente = FloatField()
    ha_perdida_copa = FloatField()
    ha_iv_tipica = FloatField()
    ha_ow_tipica = FloatField()
    ha_ni_tipica = FloatField()

    class Meta(ResultadoCorridaModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            UniqueConstraint(
                fields=["corrida", "pais"], name="unq_%(class)s_corrida_pais"
            ),
        )

        ordering: Sequence[str] = ("corrida", "pais")


class ResumenFecha(ResultadoCorridaModel):
    corrida = ForeignKey(on_delete=CASCADE, related_name="resumen_fechas", to=Corrida)
    corrida_fecha = ForeignKey(
        on_delete=CASCADE, related_name="resumenes", to=CorridaFecha
    )
    pais = CharField(db_default="", default="", max_length=2)
    ha_iv = FloatField()
    ha_ow = FloatField()
    ha_ni = FloatField()
    ha_nc = FloatField()
    ha_nd = FloatField()

    class Meta(ResultadoCorridaModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            UniqueConstraint(
                fields=["corrida_fecha", "pais"],
                name="unq_%(class)s_corridafecha_pais",
            ),
        )


class PruebaHipotesis(ResultadoCorridaModel):
    corrida = ForeignKey(on_delete=CASCADE, related_name="hipotesis", to=Corrida)
    codigo = CharField(max_length=2)
    prueba = CharField(choices=PruebaEstadistica.choices, max_length=12)
    grupo_a = CharField(max_length=100)
    grupo_b = CharField(max_length=100)
    evaluable = BooleanField()
    motivo = TextField(db_default="", default="")
    n_a = IntegerField()
    n_b = IntegerField()
    mediana_a = FloatField(null=True)
    mediana_b = FloatField(null=True)
    estadistico = FloatField(null=True)
    z = FloatField(null=True)
    p_valor = FloatField(null=True)
    efecto = FloatField(null=True)

    class Meta(ResultadoCorridaModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(evaluable=True, p_valor__isnull=False, motivo="")
                | Q(evaluable=False, p_valor__isnull=True, motivo__gt=""),
                name="chk_%(class)s_evaluable",
            ),
            CheckConstraint(
                condition=Q(codigo__in=["H1", "H2", "H3"]),
                name="chk_%(class)s_codigo",
            ),
            UniqueConstraint(
                fields=["corrida", "codigo"], name="unq_%(class)s_corrida_codigo"
            ),
        )

        ordering: Sequence[str] = ("corrida", "codigo")


class ResultadoEstanque(ResultadoCorridaModel):
    corrida = ForeignKey(on_delete=CASCADE, related_name="estanques", to=Corrida)
    estanque = ForeignKey(on_delete=RESTRICT, related_name="resultados", to=Estanque)
    area_ha = FloatField()
    cv_hh = FloatField(null=True)
    cv_hv = FloatField(null=True)
    cv = FloatField(null=True)
    activo = BooleanField()
    dist_canal_km = FloatField(null=True)
    if_vecino = FloatField(null=True)
    puntaje = FloatField(null=True)

    class Meta(ResultadoCorridaModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(activo=True, puntaje__isnull=True)
                | Q(activo=False, puntaje__isnull=False),
                name="chk_%(class)s_puntaje",
            ),
            UniqueConstraint(
                fields=["corrida", "estanque"],
                name="unq_%(class)s_corrida_estanque",
            ),
        )

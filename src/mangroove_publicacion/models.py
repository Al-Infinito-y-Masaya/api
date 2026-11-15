from typing import TYPE_CHECKING

from django.db.models import (
    CASCADE,
    RESTRICT,
    BigIntegerField,
    CharField,
    CheckConstraint,
    FloatField,
    ForeignKey,
    Q,
    UniqueConstraint,
)

from api_media.models import ApiMedia
from mangroove_analisis.models import Corrida, CorridaFecha, ResultadoCorridaModel
from mangroove_publicacion.enums import POR_FECHA, FormatoArtefacto, TipoArtefacto

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import BaseConstraint

########################################################################################


class Artefacto(ResultadoCorridaModel):
    corrida = ForeignKey(on_delete=CASCADE, related_name="artefactos", to=Corrida)
    corrida_fecha = ForeignKey(
        null=True,
        on_delete=CASCADE,
        related_name="artefactos",
        to=CorridaFecha,
    )
    tipo = CharField(choices=TipoArtefacto.choices, max_length=30)
    formato = CharField(choices=FormatoArtefacto.choices, max_length=8)
    media = ForeignKey(on_delete=RESTRICT, related_name="+", to=ApiMedia)
    sha256 = CharField(max_length=64)
    bytes = BigIntegerField()

    oeste = FloatField(null=True)
    sur = FloatField(null=True)
    este = FloatField(null=True)
    norte = FloatField(null=True)

    class Meta(ResultadoCorridaModel.Meta):  # ty: ignore[invalid-attribute-override]
        constraints: Sequence[BaseConstraint] = (
            CheckConstraint(
                condition=Q(tipo__in=TipoArtefacto.values),
                name="chk_%(class)s_tipo",
            ),
            CheckConstraint(
                condition=Q(formato__in=FormatoArtefacto.values),
                name="chk_%(class)s_formato",
            ),
            CheckConstraint(
                condition=Q(
                    formato=FormatoArtefacto.PNG,
                    oeste__isnull=False,
                    sur__isnull=False,
                    este__isnull=False,
                    norte__isnull=False,
                )
                | (
                    ~Q(formato=FormatoArtefacto.PNG)
                    & Q(
                        oeste__isnull=True,
                        sur__isnull=True,
                        este__isnull=True,
                        norte__isnull=True,
                    )
                ),
                name="chk_%(class)s_esquinas",
            ),
            CheckConstraint(
                condition=Q(tipo__in=POR_FECHA, corrida_fecha__isnull=False)
                | (~Q(tipo__in=POR_FECHA) & Q(corrida_fecha__isnull=True)),
                name="chk_%(class)s_por_fecha",
            ),
            CheckConstraint(
                condition=Q(sha256__regex=r"^[0-9a-f]{64}$") & Q(bytes__gt=0),
                name="chk_%(class)s_archivo",
            ),
            UniqueConstraint(
                fields=["corrida", "tipo", "corrida_fecha"],
                name="unq_%(class)s_corrida_tipo_fecha",
                nulls_distinct=False,
            ),
        )

        ordering: Sequence[str] = ("corrida", "tipo")

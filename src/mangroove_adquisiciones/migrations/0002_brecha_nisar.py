from datetime import UTC, datetime
from typing import TYPE_CHECKING

from django.db import migrations
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps

########################################################################################

INICIO: datetime = datetime(2026, 7, 27, 22, 3, 25, tzinfo=UTC)
FIN: datetime = datetime(2026, 8, 10, 0, 55, 27, tzinfo=UTC)

MOTIVO: str = "Brecha permanente de datos del instrumento NISAR."
FUENTE: str = "https://nisar-docs.asf.alaska.edu/availability-overview/"

########################################################################################


def sembrar(apps: StateApps, _schema_editor: BaseDatabaseSchemaEditor) -> None:
    brecha = apps.get_model("mangrooveadquisiciones", "Brecha")

    brecha.objects.get_or_create(
        rango=DateTimeTZRange(INICIO, FIN),
        defaults={"fuente_url": FUENTE, "motivo": MOTIVO},
    )


class Migration(migrations.Migration):
    dependencies = [("mangrooveadquisiciones", "0001_initial")]

    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]

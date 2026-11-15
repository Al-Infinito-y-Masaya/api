from dataclasses import asdict
from typing import TYPE_CHECKING

from django.db import migrations

from mangroove_motor.perfil import Perfil

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps

########################################################################################

PERFILES: dict[str, tuple[str, dict]] = {
    "estricto": (
        "Estricto",
        {"cusum_confianza": 0.99, "if_alta_desconectada": 0.1, "min_fechas_alta": 4},
    ),
    "predeterminado": ("Predeterminado", {}),
    "permisivo": (
        "Permisivo",
        {"cusum_confianza": 0.9, "if_alta_desconectada": 0.3, "min_fechas_alta": 2},
    ),
}

########################################################################################


def sembrar(apps: StateApps, _schema_editor: BaseDatabaseSchemaEditor) -> None:
    perfil = apps.get_model("mangrooveanalisis", "PerfilUmbrales")

    base: dict = {
        k: (v.value if hasattr(v, "value") else v) for k, v in asdict(Perfil()).items()
    }

    for codigo, (nombre, cambios) in PERFILES.items():
        if perfil.objects.filter(codigo=codigo).exists():
            continue

        perfil.objects.create(codigo=codigo, nombre=nombre, **(base | cambios))


class Migration(migrations.Migration):
    dependencies = [("mangrooveanalisis", "0002_initial")]

    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]

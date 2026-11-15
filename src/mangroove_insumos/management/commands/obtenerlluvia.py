from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError

from mangroove_comun.comandos import fecha, region_por_codigo
from mangroove_insumos.services import obtener_lluvia

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Obtiene la lluvia diaria de GPM IMERG para una región."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--region", required=True)
        parser.add_argument("--desde", required=True)
        parser.add_argument("--hasta", required=True)
        parser.add_argument(
            "--corrida-imerg", choices=("late", "final"), default="late"
        )

    @override
    def handle(self, *args: str, **options: object) -> None:
        creadas = obtener_lluvia(
            region_por_codigo(str(options["region"])),
            desde=fecha(str(options["desde"])),
            hasta=fecha(str(options["hasta"])),
            corrida_imerg=str(options["corrida_imerg"]),
        )

        if creadas < 0:
            raise CommandError("La descarga de IMERG no devolvió datos.")

        self.stdout.write(msg=self.style.SUCCESS(f"{creadas} días de lluvia nuevos."))

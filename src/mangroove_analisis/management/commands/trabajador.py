from time import sleep
from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand

from mangroove_analisis.services import ejecutar_pendientes

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Ejecuta las corridas pendientes; con --continuo, espera nuevas."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--continuo", action="store_true")
        parser.add_argument("--espera", default=30, type=int)

    @override
    def handle(self, *args: str, **options: object) -> None:
        while True:
            ejecutadas = ejecutar_pendientes()

            if ejecutadas:
                self.stdout.write(msg=f"{ejecutadas} corridas ejecutadas.")

            if not options["continuo"]:
                return

            sleep(int(options["espera"]))  # ty: ignore[invalid-argument-type]

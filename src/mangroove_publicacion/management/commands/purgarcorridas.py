from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError

from mangroove_publicacion.services import purgar_corridas

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Borra los resultados de las corridas retiradas cuyo plazo venció."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--silencioso", action="store_true")

    @override
    def handle(self, *args: str, **options: object) -> None:
        purgadas = purgar_corridas()

        if purgadas < 0:
            raise CommandError("Conteo inválido.")

        if not options["silencioso"]:
            self.stdout.write(msg=self.style.SUCCESS(f"{purgadas} corridas purgadas."))

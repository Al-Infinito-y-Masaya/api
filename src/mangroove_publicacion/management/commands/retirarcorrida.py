from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from mangroove_analisis.services import CorridaInvalidaError
from mangroove_comun.comandos import corrida_por_id
from mangroove_publicacion.services import retirar

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Retira una corrida publicada con un motivo."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("corrida")
        parser.add_argument("--motivo", required=True)

    @override
    def handle(self, *args: str, **options: object) -> None:
        try:
            corrida = retirar(
                corrida_por_id(str(options["corrida"])), str(options["motivo"])
            )
        except (CorridaInvalidaError, DatabaseError) as e:
            raise CommandError(str(e)) from e

        self.stdout.write(
            msg=self.style.SUCCESS(f"Corrida {corrida.version} retirada.")
        )

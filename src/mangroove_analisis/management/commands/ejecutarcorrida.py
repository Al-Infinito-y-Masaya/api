from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError

from mangroove_analisis.enums import EstadoCorrida
from mangroove_analisis.services import ejecutar_corrida
from mangroove_comun.comandos import corrida_por_id

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Ejecuta una corrida pendiente en este mismo proceso."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("corrida")

    @override
    def handle(self, *args: str, **options: object) -> None:
        corrida = corrida_por_id(str(options["corrida"]))

        if corrida.estado != EstadoCorrida.PENDIENTE:
            raise CommandError(f"La corrida está {corrida.estado}, no pendiente.")

        try:
            ejecutar_corrida(corrida)
        except Exception as e:
            raise CommandError(f"La corrida falló: {e}") from e

        self.stdout.write(
            msg=self.style.SUCCESS(f"Corrida {corrida.version} completada.")
        )

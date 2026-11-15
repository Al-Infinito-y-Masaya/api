from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError

from mangroove_analisis.services import CorridaInvalidaError
from mangroove_comun.comandos import corrida_por_id, usuario_por_identificador
from mangroove_comun.medios import AlmacenamientoError
from mangroove_publicacion.services import publicar

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Publica una corrida completada: capas, descargas y respaldo estático."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("corrida")
        parser.add_argument("--por", required=True)

    @override
    def handle(self, *args: str, **options: object) -> None:
        try:
            corrida = publicar(
                corrida_por_id(str(options["corrida"])),
                usuario_por_identificador(str(options["por"])),
            )
        except (CorridaInvalidaError, AlmacenamientoError) as e:
            raise CommandError(str(e)) from e

        self.stdout.write(
            msg=self.style.SUCCESS(
                f"{corrida.region.codigo} {corrida.version} publicada y vigente."
            ),
        )

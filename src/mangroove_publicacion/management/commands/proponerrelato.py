from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError

from mangroove_analisis.models import Corrida
from mangroove_analisis.services import CorridaInvalidaError
from mangroove_comun.comandos import region_por_codigo, usuario_por_identificador
from mangroove_comun.medios import AlmacenamientoError
from mangroove_publicacion.relato import RelatoError
from mangroove_publicacion.services import proponer_relato

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Elige las escenas del recorrido guiado y publica el relato de una versión."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("region")
        parser.add_argument("version")
        parser.add_argument("--por", required=True)

    @override
    def handle(self, *args: str, **options: object) -> None:
        region = region_por_codigo(str(options["region"]))

        corrida: Corrida | None = Corrida.objects.filter(
            region=region, version=str(options["version"])
        ).first()

        if corrida is None:
            raise CommandError(
                f"{region.codigo} no tiene la versión {options['version']}."
            )

        try:
            proponer_relato(corrida, usuario_por_identificador(str(options["por"])))
        except (CorridaInvalidaError, RelatoError, AlmacenamientoError) as e:
            raise CommandError(str(e)) from e

        self.stdout.write(
            msg=self.style.SUCCESS(
                f"Relato de {region.codigo} {corrida.version} publicado."
            ),
        )

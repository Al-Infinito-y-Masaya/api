from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError

from mangroove_analisis.enums import OrbitaCorrida
from mangroove_analisis.services import (
    CorridaInvalidaError,
    crear_corrida,
    perfil_vigente,
)
from mangroove_comun.comandos import fecha, region_por_codigo, usuario_por_identificador

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Crea una corrida pendiente con las adquisiciones vigentes de una madurez."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--region", required=True)
        parser.add_argument(
            "--madurez", choices=("provisional", "validado"), required=True
        )
        parser.add_argument("--perfil", default="predeterminado")
        parser.add_argument("--modelo-marea", default="")
        parser.add_argument("--fuente-lluvia", default="")
        parser.add_argument(
            "--orbita", choices=OrbitaCorrida.values, default=OrbitaCorrida.AMBAS
        )
        parser.add_argument("--tracks", nargs="*", default=[], type=int)
        parser.add_argument("--desde", default="")
        parser.add_argument("--hasta", default="")
        parser.add_argument("--por", default="")

    @override
    def handle(self, *args: str, **options: object) -> None:
        try:
            corrida = crear_corrida(
                region_por_codigo(str(options["region"])),
                madurez=str(options["madurez"]),
                perfil=perfil_vigente(str(options["perfil"])),
                modelo_marea=str(options["modelo_marea"]) or None,
                fuente_lluvia=str(options["fuente_lluvia"]),
                orbita=str(options["orbita"]),
                tracks=list(options["tracks"]),  # ty: ignore[invalid-argument-type]
                desde=fecha(str(options["desde"])) if options["desde"] else None,
                hasta=fecha(str(options["hasta"])) if options["hasta"] else None,
                usuario=usuario_por_identificador(str(options["por"]))
                if options["por"]
                else None,
            )
        except CorridaInvalidaError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(
            msg=self.style.SUCCESS(
                f"Corrida {corrida.id} versión {corrida.version}, "
                f"{corrida.n_fechas} fechas."
            ),
        )

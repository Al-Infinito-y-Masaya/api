from pathlib import Path
from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError

from mangroove_comun.comandos import region_por_codigo, usuario_por_identificador
from mangroove_insumos.enums import TipoSerie
from mangroove_insumos.services import InsumoInvalidoError, cargar_serie

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Carga un CSV de marea (datetime,tide_m) o de lluvia (date,rain_mm)."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--region", required=True)
        parser.add_argument("--tipo", choices=TipoSerie.values, required=True)
        parser.add_argument("--archivo", required=True)
        parser.add_argument("--fuente", required=True)
        parser.add_argument("--por", required=True)

    @override
    def handle(self, *args: str, **options: object) -> None:
        try:
            serie = cargar_serie(
                region=region_por_codigo(str(options["region"])),
                tipo=TipoSerie(str(options["tipo"])),
                ruta=Path(str(options["archivo"])),
                fuente=str(options["fuente"]),
                usuario=usuario_por_identificador(str(options["por"])),
            )
        except InsumoInvalidoError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(msg=self.style.SUCCESS(f"Serie serie:{serie.id} cargada."))

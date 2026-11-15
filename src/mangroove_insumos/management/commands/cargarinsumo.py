from pathlib import Path
from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError

from mangroove_comun.comandos import fecha, region_por_codigo, usuario_por_identificador
from mangroove_insumos.enums import TipoInsumo
from mangroove_insumos.services import InsumoInvalidoError, cargar_insumo

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Carga una versión nueva de un insumo auxiliar de una región."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--region", required=True)
        parser.add_argument("--tipo", choices=TipoInsumo.values, required=True)
        parser.add_argument("--archivo", required=True)
        parser.add_argument("--fuente", required=True)
        parser.add_argument("--licencia", required=True)
        parser.add_argument("--fuente-url", default="")
        parser.add_argument("--fecha-dato", default="")
        parser.add_argument("--nubes", default=None, type=float)
        parser.add_argument(
            "--por", required=True, help="Correo o usuario de la cuenta."
        )

    @override
    def handle(self, *args: str, **options: object) -> None:
        try:
            insumo = cargar_insumo(
                region=region_por_codigo(str(options["region"])),
                tipo=TipoInsumo(str(options["tipo"])),
                ruta=Path(str(options["archivo"])),
                fuente=str(options["fuente"]),
                licencia=str(options["licencia"]),
                usuario=usuario_por_identificador(str(options["por"])),
                fuente_url=str(options["fuente_url"]),
                fecha_dato=fecha(str(options["fecha_dato"]))
                if options["fecha_dato"]
                else None,
                nubes_pct=options["nubes"],
            )
        except InsumoInvalidoError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(
            msg=self.style.SUCCESS(f"Insumo {insumo.tipo} versión {insumo.version}."),
        )

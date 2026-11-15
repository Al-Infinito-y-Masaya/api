from pathlib import Path
from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError

from mangroove_motor.grilla import AoiInvalidaError
from mangroove_regiones.services import crear_region

if TYPE_CHECKING:
    from argparse import ArgumentParser

########################################################################################


class Command(BaseCommand):
    help = "Crea una región a partir de su polígono y congela su grilla."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--codigo", required=True)
        parser.add_argument("--nombre", required=True)
        parser.add_argument("--aoi", required=True, help="Archivo WKT o GeoJSON.")
        parser.add_argument(
            "--marea", nargs=2, required=True, type=float, metavar=("LON", "LAT")
        )
        parser.add_argument("--zona-horaria", default="America/Managua")
        parser.add_argument("--celda", default=100, type=int)
        parser.add_argument("--margen", default=2000, type=int)
        parser.add_argument("--zoom", default=11, type=int)

    @override
    def handle(self, *args: str, **options: object) -> None:
        try:
            region = crear_region(
                codigo=str(options["codigo"]),
                nombre=str(options["nombre"]),
                aoi=Path(str(options["aoi"])).read_text(encoding="utf-8"),
                marea=tuple(options["marea"]),  # ty: ignore[invalid-argument-type]
                zona_horaria=str(options["zona_horaria"]),
                celda_m=int(options["celda"]),  # ty: ignore[invalid-argument-type]
                margen_m=int(options["margen"]),  # ty: ignore[invalid-argument-type]
                zoom_inicial=int(options["zoom"]),  # ty: ignore[invalid-argument-type]
            )
        except AoiInvalidaError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(
            msg=self.style.SUCCESS(
                f"Región {region.codigo}: EPSG {region.epsg}, "
                f"{region.ancho} x {region.alto} celdas de {region.celda_m} m.",
            ),
        )

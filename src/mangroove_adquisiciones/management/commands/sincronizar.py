from typing import TYPE_CHECKING, override

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg, Count, Min
from django.utils.timezone import now

from mangroove_adquisiciones.models import Adquisicion
from mangroove_adquisiciones.services import (
    SincronizacionEnCursoError,
    buscar_productos,
    sincronizar,
)
from mangroove_analisis.services import proponer_corrida
from mangroove_comun.comandos import fecha, region_por_codigo, usuario_por_identificador
from mangroove_regiones.models import Region

if TYPE_CHECKING:
    from argparse import ArgumentParser
    from datetime import date

########################################################################################


class Command(BaseCommand):
    help = "Busca, recorta y consolida los productos GCOV de una o todas las regiones."

    @override
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--region", default="")
        parser.add_argument("--desde", default="2026-06-17")
        parser.add_argument("--hasta", default="")
        parser.add_argument("--por", default="")
        parser.add_argument("--estimar", action="store_true")
        parser.add_argument("--sin-corrida", action="store_true")

    @override
    def handle(self, *args: str, **options: object) -> None:
        regiones = (
            [region_por_codigo(str(options["region"]))]
            if options["region"]
            else list(Region.objects.filter(is_active=True))
        )

        desde = fecha(str(options["desde"]))
        hasta = fecha(str(options["hasta"])) if options["hasta"] else now().date()

        for region in regiones:
            if options["estimar"]:
                self.estimar(region, desde, hasta)

                continue

            try:
                sincronizacion = sincronizar(
                    region,
                    desde=desde,
                    hasta=hasta,
                    usuario=(
                        usuario_por_identificador(str(options["por"]))
                        if options["por"]
                        else None
                    ),
                )
            except SincronizacionEnCursoError as e:
                raise CommandError(str(e)) from e

            self.stdout.write(
                msg=self.style.SUCCESS(
                    f"{region.codigo}: {sincronizacion.n_encontrados} encontrados, "
                    f"{sincronizacion.n_recortados} recortados, "
                    f"{sincronizacion.n_descartados} descartados, "
                    f"{sincronizacion.n_fallidos} fallidos.",
                ),
            )

            self.por_track(region)

            if not options["sin_corrida"] and sincronizacion.n_recortados:
                corrida = proponer_corrida(region)

                if corrida is not None:
                    self.stdout.write(
                        msg=f"Corrida {corrida.id} ({corrida.version}) encolada."
                    )

    def estimar(self, region: Region, desde: date, hasta: date) -> None:
        pasadas: dict[tuple[int, str], list[int]] = {}

        for p in buscar_productos(region, desde, hasta):
            self.stdout.write(
                msg=f"{p.metadatos.granulo} {p.madurez} {p.bytes or '?'} bytes",
            )

            pasadas.setdefault((p.metadatos.track, p.metadatos.orbita), []).append(
                p.bytes or 0
            )

        for (track, orbita), tamanos in sorted(pasadas.items()):
            self.stdout.write(
                msg=f"track {track:03d} {orbita}: {len(tamanos)} productos, "
                f"{sum(tamanos) / 1e9:.1f} GB",
            )

    def por_track(self, region: Region) -> None:
        for fila in (
            Adquisicion.objects
            .filter(region=region, reemplazada=False, excluida=False)
            .values("track", "orbita")
            .annotate(
                n=Count("id", distinct=True),
                minima=Min("cobertura"),
                media=Avg("cobertura"),
                con_marea=Count("mareas__adquisicion", distinct=True),
            )
            .order_by("track", "orbita")
        ):
            self.stdout.write(
                msg=f"track {fila['track']:03d} {fila['orbita']}: {fila['n']} fechas, "
                f"cobertura mínima {fila['minima']:.0%}, media {fila['media']:.0%}, "
                f"{fila['con_marea']} con marea",
            )

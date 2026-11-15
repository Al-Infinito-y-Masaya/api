from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from io import BytesIO

from h5py import File
from numpy import (
    arange,
    array,
    bytes_,
    float32,
    full,
    int32,
    power,
    repeat,
    uint8,
    uint32,
)

from mangroove_adquisiciones.enums import Madurez
from mangroove_adquisiciones.models import Producto
from mangroove_adquisiciones.services import ProductoEncontrado
from mangroove_motor.lectura import Avance
from mangroove_motor.recorte import parsear_granulo
from mangroove_motor.sintetica import Escena
from mangroove_motor.types import Arreglo

########################################################################################

FACTOR: int = 5
MARGEN_PX: int = 25
PIXEL_M: float = 20.0

INICIO: datetime = datetime(2026, 6, 20, 0, 16, 55, tzinfo=UTC)

TRACKS: dict[int, str] = {33: "A", 98: "D", 26: "D"}

########################################################################################


class ArchivoFalso(BytesIO):
    transferido: int = 0

    @staticmethod
    def precargar(rangos: object, avance: Avance | None = None) -> int:
        return 0

    @staticmethod
    def limpiar_previos() -> None:
        return None


def granulo(t: int, track: int, crid: str = "P05023") -> str:
    inicio: datetime = INICIO + timedelta(days=4 * t)
    fin: datetime = inicio + timedelta(seconds=34)

    formato: str = "%Y%m%dT%H%M%S"

    return (
        f"NISAR_L2_PR_GCOV_{20 + t:03d}_{track:03d}_{TRACKS[track]}_082_4005_DHDH_A_"
        f"{inicio.strftime(formato)}_{fin.strftime(formato)}_{crid}_N_F_J_001"
    )


def gcov(escena: Escena, t: int) -> bytes:
    g = escena.grilla

    def nativo(db: Arreglo) -> Arreglo:
        plano = array(db).reshape(g.alto, g.ancho)

        lineal = power(10.0, plano / 10).astype(float32)

        ampliado = repeat(repeat(lineal, FACTOR, axis=0), FACTOR, axis=1)

        salida = full(
            (ampliado.shape[0] + 2 * MARGEN_PX, ampliado.shape[1] + 2 * MARGEN_PX),
            float32("nan"),
            dtype=float32,
        )

        salida[MARGEN_PX:-MARGEN_PX, MARGEN_PX:-MARGEN_PX] = ampliado

        return salida

    hh = nativo(escena.pila.hh[t])
    hv = nativo(escena.pila.hv[t])

    filas, columnas = hh.shape

    x0: float = g.x0 - MARGEN_PX * PIXEL_M
    y0: float = g.y0 + MARGEN_PX * PIXEL_M

    buffer: BytesIO = BytesIO()

    with File(buffer, "w") as h5:
        grupo = h5.create_group("science/LSAR/GCOV/grids/frequencyA")

        grupo.create_dataset("HHHH", chunks=(64, 64), data=hh)
        grupo.create_dataset("HVHV", chunks=(64, 64), data=hv)
        grupo.create_dataset(
            "mask", chunks=(64, 64), data=full((filas, columnas), 1, dtype=uint8)
        )
        grupo.create_dataset(
            "xCoordinates", data=x0 + PIXEL_M * (arange(columnas) + 0.5)
        )
        grupo.create_dataset("yCoordinates", data=y0 - PIXEL_M * (arange(filas) + 0.5))

        proyeccion = grupo.create_dataset("projection", data=uint32(g.epsg))
        proyeccion.attrs["epsg_code"] = int32(g.epsg)

        identificacion = h5.create_group("science/LSAR/identification")
        identificacion.create_dataset(
            "zeroDopplerStartTime", data=bytes_("2026-06-20T00:16:55")
        )
        identificacion.create_dataset("orbitPassDirection", data=bytes_("Ascending"))

        radar = h5.create_group("science/LSAR/GCOV/metadata/radarGrid")
        radar.create_dataset("incidenceAngle", data=float32(38.0))

    return buffer.getvalue()


@dataclass
class Nasa:
    escena: Escena
    fechas: int
    crids: dict[int, str] = field(default_factory=dict)

    def productos(self, *_: object) -> list[ProductoEncontrado]:
        encontrados: list[ProductoEncontrado] = []

        for t in range(self.fechas):
            track: int = escena_track(self.escena, t)
            nombre: str = granulo(t, track, self.crids.get(t, "P05023"))

            encontrados.append(
                ProductoEncontrado(
                    metadatos=parsear_granulo(nombre),
                    madurez=Madurez.PROVISIONAL,
                    https_url=f"https://nisar.asf.test/{nombre}.h5",
                    s3_url="",
                    bytes=1,
                    procesado_at=None,
                ),
            )

        return encontrados

    def apertura(self) -> object:
        def abrir(producto: Producto) -> ArchivoFalso:
            t: int = int(producto.granulo.split("_")[4]) - 20  # ty: ignore[unresolved-attribute]

            return ArchivoFalso(gcov(self.escena, t))

        return abrir


def escena_track(escena: Escena, t: int) -> int:
    return escena.pila.fechas[t].track


def fecha_inicio() -> date:
    return INICIO.date()


def instante(t: int) -> datetime:
    return INICIO + timedelta(days=4 * t)

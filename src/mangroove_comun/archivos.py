from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import TYPE_CHECKING

from numpy import load, save

from mangroove_comun.config import MANGROOVE_CONFIG

if TYPE_CHECKING:
    from pathlib import Path

    from mangroove_motor.types import Arreglo

########################################################################################


@dataclass(frozen=True, slots=True)
class ArchivoGuardado:
    relativa: str
    sha256: str


########################################################################################


def absoluta(relativa: str) -> Path:
    return MANGROOVE_CONFIG.MANGROOVE_DATOS / relativa


def relativa(ruta: Path) -> str:
    return str(ruta.relative_to(MANGROOVE_CONFIG.MANGROOVE_DATOS))


def suma(contenido: bytes) -> str:
    return sha256(contenido).hexdigest()


def guardar_bytes(destino: Path, contenido: bytes) -> ArchivoGuardado:
    destino.parent.mkdir(parents=True, exist_ok=True)

    parcial: Path = destino.with_name(destino.name + ".part")

    parcial.write_bytes(contenido)
    parcial.replace(destino)

    return ArchivoGuardado(relativa=relativa(destino), sha256=suma(contenido))


def guardar_arreglo(destino: Path, valores: Arreglo) -> ArchivoGuardado:
    buffer: BytesIO = BytesIO()

    save(buffer, valores, allow_pickle=False)

    return guardar_bytes(destino, buffer.getvalue())


def leer_arreglo(relativa_ruta: str, *, mapear: bool = False) -> Arreglo:
    return load(
        absoluta(relativa_ruta), allow_pickle=False, mmap_mode="r" if mapear else None
    )

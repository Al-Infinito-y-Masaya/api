from dataclasses import dataclass
from typing import TYPE_CHECKING

from numpy import asarray, zeros

from mangroove_motor.perfil import Perfil, usada_en_if_alta

if TYPE_CHECKING:
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.types import Arreglo

########################################################################################


@dataclass(frozen=True, kw_only=True, slots=True)
class Fecha:
    track: int
    marea_m: float | None = None
    lluvia_3d_mm: float | None = None


@dataclass(frozen=True, kw_only=True, slots=True)
class Pila:
    hh: Arreglo
    hv: Arreglo
    fechas: tuple[Fecha, ...]
    coherencia: Arreglo | None = None

    @property
    def t(self) -> int:
        return len(self.fechas)

    @property
    def tracks(self) -> Arreglo:
        return asarray([f.track for f in self.fechas])

    def usadas_en_if_alta(self, perfil: Perfil) -> Arreglo:
        return asarray([
            usada_en_if_alta(perfil, f.marea_m, f.lluvia_3d_mm) for f in self.fechas
        ])


@dataclass(frozen=True, kw_only=True, slots=True)
class Auxiliares:
    manglar: Arreglo
    exclusion: Arreglo | None = None
    elevacion: Arreglo | None = None
    barreras: Arreglo | None = None
    estanques: Arreglo | None = None
    paises: Arreglo | None = None
    codigos_paises: tuple[str, ...] = ()

    @classmethod
    def vacios(cls, grilla: Grilla) -> Auxiliares:
        return cls(manglar=zeros(grilla.n, dtype=bool))

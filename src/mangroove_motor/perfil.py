from dataclasses import asdict, dataclass
from enum import IntEnum, StrEnum
from hashlib import sha256
from json import dumps

########################################################################################


class Clase(IntEnum):
    NI = 0
    IV = 1
    OW = 2
    NC = 3
    ND = 4


class NivelMarea(StrEnum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"
    DESCONOCIDA = "desconocida"


class Banda(StrEnum):
    HH = "hh"
    HV = "hv"


########################################################################################


@dataclass(frozen=True, kw_only=True, slots=True)
class Perfil:
    ow_hh_db: float = -16.5
    ow_hv_db: float = -22.0
    iv_hh_db: float = -6.5
    iv_ratio_db: float = 5.0
    iv_ratio_holgura_db: float = 1.5
    cambio_hh_db: float = 3.0
    cambio_hv_db: float = 1.5
    nc_hh_db: float = -1.0
    nc_hv_db: float = -7.0
    usar_coherencia: bool = True
    coherencia_min: float = 0.40
    marea_alta_m: float = 0.55
    marea_baja_m: float = -0.55
    lluvia_max_mm: float = 60.0
    if_alta_desconectada: float = 0.20
    min_fechas_alta: int = 3
    mayoria: bool = True
    usar_elevacion: bool = False
    if_esperada_min: float = 0.5
    marea_margen_m: float = 0.05
    humedal_pendiente_max: float = 8.0
    humedal_cota_max: float = 15.0
    estables_minimas: int = 200
    sigma_db: float = 0.9
    cusum_b: int = 120
    cusum_confianza: float = 0.95
    cusum_perdida_db: float = 1.5
    cv_estanque: float = 0.45
    cv_banda: Banda = Banda.HV
    puntaje_distancia: float = 0.4
    puntaje_area: float = 0.3
    puntaje_inundacion: float = 0.3

    def huella(self) -> str:
        return sha256(dumps(asdict(self), sort_keys=True).encode()).hexdigest()


########################################################################################


def nivel_marea(perfil: Perfil, marea_m: float | None) -> NivelMarea:
    if marea_m is None:
        return NivelMarea.DESCONOCIDA

    if marea_m >= perfil.marea_alta_m:
        return NivelMarea.ALTA

    if marea_m <= perfil.marea_baja_m:
        return NivelMarea.BAJA

    return NivelMarea.MEDIA


def usada_en_if_alta(
    perfil: Perfil,
    marea_m: float | None,
    lluvia_3d_mm: float | None,
) -> bool:
    if nivel_marea(perfil, marea_m) != NivelMarea.ALTA:
        return False

    return lluvia_3d_mm is None or lluvia_3d_mm < perfil.lluvia_max_mm

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from api_core.schemas.base import DTO

########################################################################################

type Codigo = Annotated[
    str, StringConstraints(max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
]
type Version = Annotated[
    str, StringConstraints(max_length=20, pattern=r"^\d+\.\d+\.\d+$")
]
type FechaId = Annotated[
    str,
    StringConstraints(max_length=20, pattern=r"^\d{4}-\d{2}-\d{2}_\d{3}_(asc|desc)$"),
]

########################################################################################


class RegionPath(DTO):
    region: Codigo


class VersionPath(RegionPath):
    version: Version


class CapaPath(VersionPath):
    capa: Literal["if_alta", "if", "desconexion", "p_error", "cambio"]


class FechaCapaPath(VersionPath):
    fecha: FechaId
    capa: Literal["rgb", "clases"]


class CeldaPath(VersionPath):
    celda: Annotated[str, StringConstraints(max_length=24, pattern=r"^c_\d+_\d+$")]


class PuntoQuery(DTO):
    lon: Annotated[float, Field(ge=-180, le=180)]
    lat: Annotated[float, Field(ge=-90, le=90)]


class EstanquesQuery(DTO):
    clase: Literal["", "activo", "abandonado"] = ""
    orden: Literal["puntaje", "area", "distancia", "inundacion"] = "puntaje"


class ResumenQuery(DTO):
    formato: Literal["json", "csv"] = "json"


class ExploracionPost(DTO):
    ow_hh_db: Annotated[float, Field(ge=-30, le=-5)] | None = None
    ow_hv_db: Annotated[float, Field(ge=-35, le=-10)] | None = None
    iv_hh_db: Annotated[float, Field(ge=-15, le=5)] | None = None
    iv_ratio_db: Annotated[float, Field(ge=0, le=15)] | None = None
    marea_alta_m: Annotated[float, Field(ge=-1, le=3)] | None = None
    lluvia_max_mm: Annotated[float, Field(ge=0, le=500)] | None = None
    if_alta_desconectada: Annotated[float, Field(ge=0, le=1)] | None = None
    min_fechas_alta: Annotated[int, Field(ge=1, le=20)] | None = None
    mayoria: bool | None = None

    def cambios(self) -> dict:
        return self.model_dump(exclude_none=True)

from pathlib import Path
from typing import Final, Literal

from pydantic import NonNegativeInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from api_utils.env import ROOT

########################################################################################


class MangrooveConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MANGROOVE_DATOS: Path = ROOT / ".datos"
    MANGROOVE_MAREA: Path | None = None
    MANGROOVE_MODELO_MAREA: str = "FES2014"
    MANGROOVE_ACCESO: Literal["auto", "https", "s3"] = "auto"
    MANGROOVE_HILOS: NonNegativeInt = 0
    MANGROOVE_CDN_PREFIJO: str = "mangroove"
    MANGROOVE_CODIGO: str = "local"
    MANGROOVE_DIAS_PURGA: int = 30

    EARTHDATA_TOKEN: SecretStr = SecretStr(secret_value="")

    @property
    def recortes(self) -> Path:
        return self.MANGROOVE_DATOS / "recortes"

    @property
    def grillas(self) -> Path:
        return self.MANGROOVE_DATOS / "grillas"

    @property
    def insumos(self) -> Path:
        return self.MANGROOVE_DATOS / "insumos"

    @property
    def cubos(self) -> Path:
        return self.MANGROOVE_DATOS / "cubos"


########################################################################################

MANGROOVE_CONFIG: Final[MangrooveConfig] = MangrooveConfig()

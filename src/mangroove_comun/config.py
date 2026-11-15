from pathlib import Path
from typing import Final, Literal

from pydantic import NonNegativeInt, SecretStr, field_validator
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
    MANGROOVE_MODELO_MAREA: str = "GOT4.10_nc"
    MANGROOVE_ACCESO: Literal["auto", "https", "s3"] = "auto"
    MANGROOVE_HILOS: NonNegativeInt = 0
    MANGROOVE_URL_ARCHIVOS: str = "http://127.0.0.1:8080/archivos"
    MANGROOVE_CODIGO: str = "local"
    MANGROOVE_DIAS_PURGA: int = 30

    EARTHDATA_TOKEN: SecretStr = SecretStr(secret_value="")

    @field_validator("MANGROOVE_MAREA", mode="before")
    @classmethod
    def marea_vacia(cls, valor: object) -> object:
        return valor or None

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

    @property
    def archivos(self) -> Path:
        return self.MANGROOVE_DATOS / "archivos"


########################################################################################

MANGROOVE_CONFIG: Final[MangrooveConfig] = MangrooveConfig()

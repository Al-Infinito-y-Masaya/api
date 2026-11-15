from collections.abc import Generator
from importlib import import_module
from pathlib import Path

from django.apps import apps
from django.test.utils import override_settings
from pytest import MonkeyPatch, fixture

from api_auth.models import ApiUser
from mangroove_comun.config import MANGROOVE_CONFIG

########################################################################################

LOCMEM: dict = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "mangroove-tests",
    },
}

SEMILLAS: tuple[str, ...] = (
    "mangroove_adquisiciones.migrations.0002_brecha_nisar",
    "mangroove_analisis.migrations.0003_perfiles_iniciales",
)

########################################################################################


@fixture(autouse=True)
def datos(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    carpeta: Path = tmp_path / "datos"

    monkeypatch.setattr(MANGROOVE_CONFIG, "MANGROOVE_DATOS", carpeta)
    monkeypatch.setattr(MANGROOVE_CONFIG, "MANGROOVE_MAREA", None)

    return carpeta


@fixture
def cache_local() -> Generator[None]:
    with override_settings(CACHES=LOCMEM):
        yield


@fixture
def operador(db: None) -> ApiUser:
    return ApiUser.objects.create_user(
        username="operador",
        email="operador@mangroove.earth",
        password="CONTRASEÑA-larga-123!",
    )


@fixture
def semillas(db: None) -> None:
    for modulo in SEMILLAS:
        import_module(modulo).sembrar(apps, None)

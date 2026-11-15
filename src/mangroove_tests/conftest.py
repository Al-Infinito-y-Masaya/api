from collections.abc import Generator
from pathlib import Path

from django.test.utils import override_settings
from pytest import MonkeyPatch, fixture
from respx import MockRouter, mock

from api_auth.models import ApiUser
from api_media.services.bunny import BUNNY_CLIENT
from mangroove_comun.config import MANGROOVE_CONFIG

########################################################################################

LOCMEM: dict = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "mangroove-tests",
    },
}

########################################################################################


@fixture(autouse=True)
def bunny() -> Generator[MockRouter]:
    with mock(assert_all_called=False) as router:
        almacen: str = BUNNY_CLIENT.storage_url("")

        router.put(name="put", url__startswith=almacen).respond(201)
        router.delete(name="delete", url__startswith=almacen).respond(200)

        yield router


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

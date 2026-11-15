from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image
from rasterio.io import MemoryFile

from api_media.enums import MediaVisibility
from api_media.models import ApiMedia
from mangroove_comun.archivos import guardar_bytes, suma
from mangroove_comun.config import MANGROOVE_CONFIG

if TYPE_CHECKING:
    from pathlib import Path

    from api_auth.models import ApiUser

########################################################################################

MIME_PNG: str = "image/png"
MIME_TIFF: str = "image/tiff"

########################################################################################


class AlmacenamientoError(RuntimeError):
    pass


def llave(visibilidad: MediaVisibility, ruta: str) -> str:
    return f"{visibilidad.value}/{ruta}"


def ruta_local(storage_key: str) -> Path:
    return MANGROOVE_CONFIG.archivos / storage_key


def dimensiones(contenido: bytes, mime: str) -> tuple[int | None, int | None]:
    if mime == MIME_TIFF:
        with MemoryFile(contenido) as memoria, memoria.open() as raster:
            return raster.width, raster.height

    if mime != MIME_PNG:
        return None, None

    with Image.open(BytesIO(contenido)) as imagen:
        return imagen.width, imagen.height


def escribir(storage_key: str, contenido: bytes) -> None:
    try:
        guardar_bytes(ruta_local(storage_key), contenido)
    except OSError as e:
        raise AlmacenamientoError(f"No se pudo almacenar {storage_key}.") from e


def escribir_publico(ruta: str, contenido: bytes) -> None:
    escribir(llave(MediaVisibility.PUBLIC, ruta), contenido)


def subir(
    *,
    contenido: bytes,
    mime: str,
    ruta: str,
    visibilidad: MediaVisibility,
    usuario: ApiUser,
) -> ApiMedia:
    storage_key: str = llave(visibilidad, ruta)

    existente: ApiMedia | None = ApiMedia.objects.filter(
        storage_key=storage_key
    ).first()

    checksum: str = suma(contenido)

    if existente is not None:
        if existente.checksum != checksum:
            raise AlmacenamientoError(f"{storage_key} ya existe con otro contenido.")

        if not ruta_local(storage_key).exists():
            escribir(storage_key, contenido)

        return existente

    escribir(storage_key, contenido)

    ancho, alto = dimensiones(contenido, mime)

    try:
        return ApiMedia.objects.create(
            checksum=checksum,
            height=alto,
            mime=mime,
            size=len(contenido),
            storage_key=storage_key,
            uploaded_by=usuario,
            visibility=visibilidad,
            width=ancho,
        )
    except Exception:
        ruta_local(storage_key).unlink(missing_ok=True)

        raise


def borrar(media: ApiMedia) -> None:
    ruta_local(media.storage_key).unlink(missing_ok=True)  # ty: ignore[invalid-argument-type]


def url_publica(media: ApiMedia) -> str:
    ruta: str = media.storage_key.removeprefix(f"{MediaVisibility.PUBLIC.value}/")  # ty: ignore[unresolved-attribute]

    return f"{MANGROOVE_CONFIG.MANGROOVE_URL_ARCHIVOS.rstrip('/')}/{ruta}"

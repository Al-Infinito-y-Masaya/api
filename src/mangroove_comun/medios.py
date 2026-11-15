from contextlib import suppress
from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image
from asgiref.sync import async_to_sync
from rasterio.io import MemoryFile

from api_media.models import ApiMedia
from api_media.services.bunny import BUNNY_CLIENT
from api_media.services.media import STORAGE_ERRORS
from mangroove_comun.archivos import suma
from mangroove_comun.config import MANGROOVE_CONFIG

if TYPE_CHECKING:
    from api_auth.models import ApiUser
    from api_media.enums import MediaVisibility

########################################################################################

MIME_PNG: str = "image/png"
MIME_TIFF: str = "image/tiff"

########################################################################################


class AlmacenamientoError(RuntimeError):
    pass


def llave(visibilidad: MediaVisibility, ruta: str) -> str:
    return f"{visibilidad.value}/{MANGROOVE_CONFIG.MANGROOVE_CDN_PREFIJO}/{ruta}"


def dimensiones(contenido: bytes, mime: str) -> tuple[int | None, int | None]:
    if mime == MIME_TIFF:
        with MemoryFile(contenido) as memoria, memoria.open() as raster:
            return raster.width, raster.height

    if mime != MIME_PNG:
        return None, None

    with Image.open(BytesIO(contenido)) as imagen:
        return imagen.width, imagen.height


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
        if existente.checksum == checksum:
            return existente

        raise AlmacenamientoError(f"{storage_key} ya existe con otro contenido.")

    try:
        async_to_sync(BUNNY_CLIENT.put)(
            checksum=checksum,
            content=contenido,
            content_type=mime,
            storage_key=storage_key,
        )
    except STORAGE_ERRORS as e:
        raise AlmacenamientoError(f"No se pudo almacenar {storage_key}.") from e

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
        with suppress(*STORAGE_ERRORS):
            async_to_sync(BUNNY_CLIENT.delete)(storage_key=storage_key)

        raise


def borrar(media: ApiMedia) -> None:
    with suppress(*STORAGE_ERRORS):
        async_to_sync(BUNNY_CLIENT.delete)(storage_key=media.storage_key)  # ty: ignore[invalid-argument-type]


def url_publica(media: ApiMedia) -> str:
    return BUNNY_CLIENT.public_url(media.storage_key)  # ty: ignore[invalid-argument-type]

from bisect import bisect_right
from collections import OrderedDict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from io import RawIOBase
from threading import Lock
from time import sleep
from typing import override
from urllib.parse import urlparse

from boto3 import client as cliente_aws
from botocore.config import Config
from botocore.exceptions import ClientError
from requests import (
    Response,
    Session,
    get as peticion_get,
    put as peticion_put,
)
from requests.adapters import HTTPAdapter
from requests.exceptions import (
    ChunkedEncodingError,
    ConnectionError as ErrorConexion,
    RequestException,
    Timeout,
)

########################################################################################

BLOQUE: int = 2 * 1024 * 1024
BLOQUES_EN_CACHE: int = 48
PETICION_MAXIMA: int = 4 * 1024 * 1024
HUECO_MAXIMO: int = 256 * 1024
INTENTOS: int = 6
INTENTOS_RANGO: int = 4
ESTADO_PARCIAL: int = 206
ESTADO_DEMASIADAS: int = 429
ESTADO_SERVIDOR: int = 500
ESTADOS_RECHAZO: frozenset[int] = frozenset({400, 401, 403})
ESTADOS_SIN_PERMISO: frozenset[int] = frozenset({401, 403})
REGION_NISAR: str = "us-west-2"
URL_CREDENCIALES: str = "https://nisar.asf.earthdatacloud.nasa.gov/s3credentials"
IMDS: str = "http://169.254.169.254/latest"
RENOVAR_ANTES: timedelta = timedelta(minutes=5)
ERRORES_TOKEN: frozenset[str] = frozenset({
    "ExpiredToken",
    "InvalidToken",
    "TokenRefreshRequired",
})
ERRORES_ACCESO: frozenset[str] = frozenset({"AccessDenied", "403", "Forbidden"})

type Avance = Callable[[int, int], None]

########################################################################################


class LecturaRemotaError(OSError):
    pass


class AccesoDenegadoError(LecturaRemotaError):
    pass


########################################################################################


class ArchivoRemoto(RawIOBase):
    def __init__(self, url: str, sesion: Session | None, *, hilos: int = 6) -> None:
        super().__init__()

        self.url: str = url
        self.sesion: Session | None = sesion
        self.hilos: int = max(1, hilos)
        self.cache: OrderedDict[int, bytes] = OrderedDict()
        self.previos: dict[int, bytes] = {}
        self.inicios: list[int] = []
        self.posicion: int = 0
        self.transferido: int = 0
        self.peticiones: int = 0
        self.candado: Lock = Lock()
        self.limpia: Session = Session()
        self.limpia.mount("https://", HTTPAdapter(pool_maxsize=self.hilos + 2))
        self.tamano: int = 0
        self.final: str = url
        self.lectora: Session = self.limpia

        self.resolver()

    @staticmethod
    def http(  # ruff: ignore[too-many-arguments]
        sesion: Session,
        url: str,
        encabezados: dict,
        *,
        espera: float,
        seguir: bool = True,
        flujo: bool = False,
    ) -> Response:
        error: str = ""

        for intento in range(INTENTOS):
            try:
                respuesta: Response = sesion.get(
                    url,
                    allow_redirects=seguir,
                    headers=encabezados,
                    stream=flujo,
                    timeout=espera,
                )
            except (ErrorConexion, Timeout, ChunkedEncodingError) as e:
                error = type(e).__name__
            else:
                if (
                    respuesta.status_code != ESTADO_DEMASIADAS
                    and respuesta.status_code < ESTADO_SERVIDOR
                ):
                    return respuesta

                error = f"HTTP {respuesta.status_code}"
                respuesta.close()

            if intento < INTENTOS - 1:
                sleep(2 ** (intento + 1))

        raise LecturaRemotaError(
            f"La lectura falló tras {INTENTOS} intentos ({error})."
        )

    def resolver(self) -> None:
        sesion: Session = self.sesion or self.limpia

        with self.candado:
            respuesta: Response = self.http(
                sesion,
                self.url,
                {"Range": "bytes=0-0"},
                espera=120,
                flujo=True,
            )

            rango: str | None = respuesta.headers.get("Content-Range")
            codigo: int = respuesta.status_code
            final: str = respuesta.url

            respuesta.close()

            if codigo in ESTADOS_SIN_PERMISO:
                raise AccesoDenegadoError(
                    f"HTTP {codigo}: Earthdata no autorizó la lectura.",
                )

            if codigo != ESTADO_PARCIAL or not rango:
                raise LecturaRemotaError(
                    f"HTTP {codigo}: el servidor no aceptó lecturas parciales.",
                )

            self.tamano = int(rango.split("/")[-1])
            self.final = final
            self.lectora = (
                sesion
                if urlparse(final).netloc == urlparse(self.url).netloc
                else self.limpia
            )

    def obtener(self, a: int, b: int) -> bytes:
        esperado: int = b - a + 1

        for intento in range(INTENTOS_RANGO):
            respuesta: Response = self.http(
                self.lectora,
                self.final,
                {"Range": f"bytes={a}-{b}"},
                espera=180,
            )

            if respuesta.status_code == ESTADO_PARCIAL:
                if len(respuesta.content) != esperado:
                    continue

                with self.candado:
                    self.transferido += esperado
                    self.peticiones += 1

                return respuesta.content

            if (
                respuesta.status_code in ESTADOS_RECHAZO
                and intento < INTENTOS_RANGO - 1
            ):
                self.resolver()
                continue

            raise LecturaRemotaError(f"HTTP {respuesta.status_code} al leer {a}-{b}.")

        raise LecturaRemotaError(f"No se pudo leer el rango {a}-{b}.")

    def precargar(
        self,
        rangos: Iterable[tuple[int, int]],
        avance: Avance | None = None,
    ) -> int:
        ordenados: list[tuple[int, int]] = sorted({(o, n) for o, n in rangos if n})

        grupos: list[list] = []

        for desplazamiento, tamano in ordenados:
            if (
                grupos
                and desplazamiento - grupos[-1][1] <= HUECO_MAXIMO
                and desplazamiento + tamano - grupos[-1][0] <= PETICION_MAXIMA
            ):
                grupos[-1][1] = max(grupos[-1][1], desplazamiento + tamano)
                grupos[-1][2].append((desplazamiento, tamano))
            else:
                grupos.append([
                    desplazamiento,
                    desplazamiento + tamano,
                    [(desplazamiento, tamano)],
                ])

        def traer(grupo: list) -> list[tuple[int, bytes]]:
            inicio, fin, partes = grupo

            datos: bytes = self.obtener(inicio, fin - 1)

            return [(o, datos[o - inicio : o - inicio + n]) for o, n in partes]

        total: int = sum(fin - inicio for inicio, fin, _ in grupos)
        hecho: int = 0

        with ThreadPoolExecutor(self.hilos) as ejecutor:
            futuros: dict = {ejecutor.submit(traer, g): g[1] - g[0] for g in grupos}

            try:
                for futuro in as_completed(futuros):
                    for desplazamiento, datos in futuro.result():
                        self.previos[desplazamiento] = datos

                    hecho += futuros[futuro]

                    if avance is not None:
                        avance(hecho, total)
            except BaseException:
                for futuro in futuros:
                    futuro.cancel()

                raise

        self.inicios = sorted(self.previos)

        return len(grupos)

    def limpiar_previos(self) -> None:
        self.previos = {}
        self.inicios = []

    def bloque(self, k: int) -> bytes:
        if k in self.cache:
            self.cache.move_to_end(k)

            return self.cache[k]

        inicio: int = k * BLOQUE

        datos: bytes = self.obtener(inicio, min(self.tamano, inicio + BLOQUE) - 1)

        self.cache[k] = datos

        if len(self.cache) > BLOQUES_EN_CACHE:
            self.cache.popitem(last=False)

        return datos

    @override
    def readable(self) -> bool:
        return True

    @override
    def seekable(self) -> bool:
        return True

    @override
    def tell(self) -> int:
        return self.posicion

    @override
    def seek(self, desplazamiento: int, desde: int = 0) -> int:
        if desde == 0:
            self.posicion = desplazamiento
        elif desde == 1:
            self.posicion += desplazamiento
        else:
            self.posicion = self.tamano + desplazamiento

        return self.posicion

    @override
    def readinto(self, buffer: memoryview | bytearray) -> int:  # ty: ignore[invalid-method-override]
        n: int = min(len(buffer), max(0, self.tamano - self.posicion))

        if n == 0:
            return 0

        vista: memoryview = memoryview(buffer).cast("B")

        i: int = bisect_right(self.inicios, self.posicion) - 1

        if i >= 0:
            inicio: int = self.inicios[i]
            datos: bytes = self.previos[inicio]

            if self.posicion + n <= inicio + len(datos):
                vista[:n] = datos[self.posicion - inicio : self.posicion - inicio + n]
                self.posicion += n

                return n

        if n >= 4 * BLOQUE:
            vista[:n] = self.obtener(self.posicion, self.posicion + n - 1)
        else:
            leido: int = 0

            while leido < n:
                k, desplazamiento = divmod(self.posicion + leido, BLOQUE)

                bloque: bytes = self.bloque(k)

                tomar: int = min(len(bloque) - desplazamiento, n - leido)

                if tomar <= 0:
                    raise LecturaRemotaError(
                        "El bloque remoto es más corto de lo esperado."
                    )

                vista[leido : leido + tomar] = bloque[
                    desplazamiento : desplazamiento + tomar
                ]
                leido += tomar

        self.posicion += n

        return n

    @override
    def close(self) -> None:
        self.cache.clear()
        self.limpiar_previos()
        self.limpia.close()

        super().close()


########################################################################################


class CredencialesS3:
    def __init__(self, sesion: Session) -> None:
        self.sesion: Session = sesion
        self.candado: Lock = Lock()
        self.actual: object | None = None
        self.vence: datetime = datetime.min.replace(tzinfo=UTC)

    def cliente(self, *, forzar: bool = False) -> object:
        with self.candado:
            ahora: datetime = datetime.now(UTC)

            if forzar or self.actual is None or self.vence - ahora < RENOVAR_ANTES:
                respuesta: Response = self.sesion.get(URL_CREDENCIALES, timeout=60)

                if not respuesta.ok:
                    raise AccesoDenegadoError(
                        f"s3credentials respondió HTTP {respuesta.status_code}.",
                    )

                datos: dict = respuesta.json()

                try:
                    self.vence = datetime.fromisoformat(str(datos["expiration"]))
                except KeyError, ValueError:
                    self.vence = ahora + timedelta(minutes=50)

                if self.vence.tzinfo is None:
                    self.vence = self.vence.replace(tzinfo=UTC)

                self.actual = cliente_aws(
                    "s3",
                    aws_access_key_id=datos["accessKeyId"],
                    aws_secret_access_key=datos["secretAccessKey"],
                    aws_session_token=datos["sessionToken"],
                    config=Config(
                        max_pool_connections=32,
                        retries={"max_attempts": 8, "mode": "adaptive"},
                    ),
                    region_name=REGION_NISAR,
                )

            return self.actual


class ArchivoS3(ArchivoRemoto):
    def __init__(
        self, url_s3: str, credenciales: CredencialesS3, *, hilos: int = 16
    ) -> None:
        self.credenciales: CredencialesS3 = credenciales
        self.cubeta, self.llave = url_s3.removeprefix("s3://").split("/", 1)

        super().__init__(url_s3, None, hilos=hilos)

    def llamar(self, operacion: Callable[[object], dict]) -> dict:
        for intento in range(3):
            try:
                return operacion(self.credenciales.cliente(forzar=intento > 0))
            except ClientError as e:
                codigo: str = str(e.response.get("Error", {}).get("Code", ""))

                if codigo in ERRORES_TOKEN and intento < 2:  # ruff: ignore[magic-value-comparison]
                    continue

                if codigo in ERRORES_ACCESO:
                    raise AccesoDenegadoError(
                        "S3 negó el acceso: la lectura directa solo funciona "
                        "desde us-west-2.",
                    ) from e

                raise

        raise LecturaRemotaError("No se pudieron renovar las credenciales de S3.")

    @override
    def resolver(self) -> None:
        cabecera: dict = self.llamar(
            lambda c: c.head_object(Bucket=self.cubeta, Key=self.llave),  # ty: ignore[unresolved-attribute]
        )

        self.tamano = int(cabecera["ContentLength"])
        self.final = self.url

    @override
    def obtener(self, a: int, b: int) -> bytes:
        esperado: int = b - a + 1
        error: str = ""

        for intento in range(5):
            try:
                respuesta: dict = self.llamar(
                    lambda c: c.get_object(  # ty: ignore[unresolved-attribute]
                        Bucket=self.cubeta,
                        Key=self.llave,
                        Range=f"bytes={a}-{b}",
                    ),
                )

                datos: bytes = respuesta["Body"].read()
            except AccesoDenegadoError:
                raise
            except (ClientError, OSError, RequestException) as e:
                error = type(e).__name__
            else:
                if len(datos) == esperado:
                    with self.candado:
                        self.transferido += esperado
                        self.peticiones += 1

                    return datos

                error = f"respuesta incompleta ({len(datos)} de {esperado} bytes)"

            sleep(2 ** (intento + 1))

        raise LecturaRemotaError(f"S3: no se pudo leer {a}-{b} ({error}).")


########################################################################################


def region_aws() -> str | None:
    try:
        token: str = peticion_put(
            f"{IMDS}/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            timeout=0.5,
        ).text

        respuesta: Response = peticion_get(
            f"{IMDS}/meta-data/placement/region",
            headers={"X-aws-ec2-metadata-token": token},
            timeout=0.5,
        )
    except RequestException:
        return None

    return respuesta.text.strip() if respuesta.ok else None


def usar_s3(modo: str) -> bool:
    if modo != "auto":
        return modo == "s3"

    return region_aws() == REGION_NISAR

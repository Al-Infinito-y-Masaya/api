from datetime import UTC, datetime, timedelta
from io import BytesIO
from json import dumps
from pathlib import Path

from botocore.exceptions import ClientError
from h5py import File
from numpy import isfinite
from pytest import MonkeyPatch, approx, fixture, raises
from requests import Response, Session
from requests.exceptions import (
    ConnectionError as ErrorConexion,
    RequestException,
)
from requests.structures import CaseInsensitiveDict

from mangroove_motor import lectura
from mangroove_motor.agregacion import agregar, cobertura
from mangroove_motor.lectura import (
    AccesoDenegadoError,
    ArchivoRemoto,
    ArchivoS3,
    CredencialesS3,
    LecturaRemotaError,
    region_aws,
    usar_s3,
)
from mangroove_motor.recorte import (
    ProductoInvalidoError,
    bytes_ventana,
    chunks_ventana,
    escribir_recorte,
    leer_recorte,
    leer_ventana,
    parsear_granulo,
)
from mangroove_tests.test_motor.gcov import GRANULO, escribir_gcov, grilla_region

########################################################################################

URL: str = "https://datapool.asf.alaska.edu/GCOV/NISAR/producto.h5"
FIRMADA: str = "https://cumulus.s3.amazonaws.com/producto.h5?firma=1"


def respuesta(
    estado: int, contenido: bytes = b"", encabezados: dict | None = None, url: str = URL
) -> Response:
    r = Response()
    r.status_code = estado
    r._content = contenido  # ruff: ignore[private-member-access]
    r.headers = CaseInsensitiveDict(encabezados or {})
    r.raw = BytesIO(contenido)
    r.url = url

    return r


class SesionFalsa(Session):
    def __init__(
        self,
        contenido: bytes = b"",
        *,
        final: str = URL,
        fallas: list[int] | None = None,
    ) -> None:
        super().__init__()

        self.contenido: bytes = contenido
        self.final: str = final
        self.fallas: list[int] = list(fallas or [])
        self.pedidos: list[str] = []

    def get(self, url: str, **kwargs: object) -> Response:  # ty: ignore[invalid-method-override]
        encabezados: dict = kwargs.get("headers") or {}  # ty: ignore[invalid-assignment]

        self.pedidos.append(encabezados.get("Range", ""))

        if self.fallas:
            codigo = self.fallas.pop(0)

            if codigo == 0:
                raise ErrorConexion("corte")

            return respuesta(codigo)

        inicio, fin = (
            int(v) for v in encabezados["Range"].removeprefix("bytes=").split("-")
        )

        return respuesta(
            206,
            self.contenido[inicio : fin + 1],
            {"Content-Range": f"bytes {inicio}-{fin}/{len(self.contenido)}"},
            self.final,
        )


@fixture(autouse=True)
def sin_esperas(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(lectura, "sleep", lambda _: None)


@fixture
def producto(tmp_path: Path) -> bytes:
    return escribir_gcov(tmp_path / f"{GRANULO}.h5").read_bytes()


########################################################################################


def test_remote_file_reads_only_the_window(producto: bytes) -> None:
    sesion = SesionFalsa(producto)

    archivo = ArchivoRemoto(URL, sesion, hilos=2)

    with File(archivo, "r") as h5:
        recorte = leer_ventana(
            h5, grilla_region(), margen_m=0.0, granulo=GRANULO, archivo=archivo
        )

    archivo.close()

    assert recorte is not None
    assert recorte.hh.shape == (40, 50)
    assert recorte.ventana.columnas == (100, 150)
    assert recorte.incidencia == approx(35.5)
    assert recorte.orbita == "Ascending"
    assert recorte.pixel_m == approx(20.0)
    assert archivo.peticiones > 0
    assert archivo.previos == {}


def test_prefetch_merges_nearby_ranges_and_reports_progress(producto: bytes) -> None:
    archivo = ArchivoRemoto(URL, SesionFalsa(producto))

    avances: list[tuple[int, int]] = []

    grupos = archivo.precargar(
        [(0, 10), (20, 10), (900_000, 5), (0, 0)],
        lambda hecho, total: avances.append((hecho, total)),
    )

    assert grupos == 2
    assert sorted(archivo.previos) == [0, 20, 900_000]
    assert archivo.previos[20] == producto[20:30]
    assert avances[-1][0] == avances[-1][1]

    archivo.seek(22)

    assert archivo.read(4) == producto[22:26]


def test_window_aggregates_onto_the_region_grid(
    producto: bytes, tmp_path: Path
) -> None:
    grilla = grilla_region()

    ruta = tmp_path / "local.h5"
    ruta.write_bytes(producto)

    with File(ruta, "r") as h5:
        recorte = leer_ventana(h5, grilla, margen_m=200.0, granulo=GRANULO)

    assert recorte is not None

    agregado = agregar(
        hh=recorte.hh,
        hv=recorte.hv,
        xs=recorte.xs,
        ys=recorte.ys,
        epsg=recorte.epsg,
        grilla=grilla,
        mascara=recorte.mascara,
    )

    db = agregado.en_db()

    assert db[0] == approx(-13.0103, abs=1e-3)
    assert cobertura(db, isfinite(db[0])) == approx(1.0)


def test_crop_round_trips_through_disk(producto: bytes, tmp_path: Path) -> None:
    with File(BytesIO(producto), "r") as h5:
        recorte = leer_ventana(h5, grilla_region(), margen_m=100.0, granulo=GRANULO)

    assert recorte is not None

    escrito = escribir_recorte(tmp_path / "recortes" / "a.h5", recorte, URL)

    leido = leer_recorte(escrito.ruta)

    assert escrito.bytes == escrito.ruta.stat().st_size
    assert len(escrito.sha256) == 64
    assert not (tmp_path / "recortes" / "a.h5.part").exists()
    assert leido.hh.shape == recorte.hh.shape
    assert leido.granulo == GRANULO
    assert leido.ventana == recorte.ventana
    assert leido.incidencia == recorte.incidencia


def test_scalar_incidence_and_out_of_area_products(tmp_path: Path) -> None:
    ruta = escribir_gcov(tmp_path / "plano.h5", incidencia_3d=False)

    with File(ruta, "r") as h5:
        recorte = leer_ventana(h5, grilla_region(), margen_m=0.0, granulo=GRANULO)

        assert recorte is not None
        assert recorte.incidencia == approx(40.0)

    lejos = escribir_gcov(tmp_path / "lejos.h5", x0=900_000.0)

    with File(lejos, "r") as h5:
        assert leer_ventana(h5, grilla_region(), margen_m=0.0, granulo=GRANULO) is None


def test_products_without_hv_are_rejected(tmp_path: Path) -> None:
    ruta = escribir_gcov(tmp_path / "solo_hh.h5", con_hv=False)

    with File(ruta, "r") as h5, raises(ProductoInvalidoError):
        leer_ventana(h5, grilla_region(), margen_m=0.0, granulo=GRANULO)


def test_window_byte_estimates(producto: bytes) -> None:
    with File(BytesIO(producto), "r") as h5:
        recorte = leer_ventana(h5, grilla_region(), margen_m=0.0, granulo=GRANULO)

        assert recorte is not None

        dataset = h5["science/LSAR/GCOV/grids/frequencyA/HHHH"]

        assert len(chunks_ventana(dataset, recorte.ventana)) == 4
        assert bytes_ventana(dataset, recorte.ventana) > 0


def test_granule_names_parse_or_fail() -> None:
    metadatos = parsear_granulo(f"https://x/{GRANULO}.h5?token=1")

    assert metadatos.track == 33
    assert metadatos.frame == 8
    assert metadatos.ciclo == 34
    assert metadatos.orbita == "asc"
    assert metadatos.crid == "P05036"
    assert metadatos.inicio == datetime(2026, 10, 26, 11, 22, 21, tzinfo=UTC)

    with raises(ProductoInvalidoError):
        parsear_granulo("S1A_IW_GRDH_1SDV_20261026.zip")


########################################################################################


def test_signed_redirects_use_a_clean_session(
    producto: bytes, monkeypatch: MonkeyPatch
) -> None:
    limpia = SesionFalsa(producto, final=FIRMADA)

    monkeypatch.setattr(lectura, "Session", lambda: limpia)

    sesion = SesionFalsa(producto, final=FIRMADA)

    archivo = ArchivoRemoto(URL, sesion)

    assert archivo.lectora is limpia
    assert archivo.read(4) == producto[:4]


def test_retries_then_reports_the_failure(producto: bytes) -> None:
    sesion = SesionFalsa(producto, fallas=[0, 503])

    archivo = ArchivoRemoto(URL, sesion)

    assert archivo.tamano == len(producto)

    with raises(LecturaRemotaError):
        ArchivoRemoto(URL, SesionFalsa(producto, fallas=[503] * 6))


def test_unauthorized_and_range_less_servers_are_rejected(producto: bytes) -> None:
    with raises(AccesoDenegadoError):
        ArchivoRemoto(URL, SesionFalsa(producto, fallas=[401]))

    with raises(LecturaRemotaError):
        ArchivoRemoto(URL, SesionFalsa(producto, fallas=[200]))


def test_reads_across_blocks_and_large_reads(producto: bytes) -> None:
    archivo = ArchivoRemoto(URL, SesionFalsa(producto))

    archivo.seek(lectura.BLOQUE - 2)

    assert archivo.read(4) == producto[lectura.BLOQUE - 2 : lectura.BLOQUE + 2]

    archivo.seek(-4, 2)

    assert archivo.read(10) == producto[-4:]
    assert archivo.read(1) == b""

    archivo.seek(0)
    archivo.seek(3, 1)

    assert archivo.tell() == 3
    assert archivo.readable()
    assert archivo.seekable()


def test_expired_signed_urls_are_resolved_again(producto: bytes) -> None:
    sesion = SesionFalsa(producto)

    archivo = ArchivoRemoto(URL, sesion)

    sesion.fallas = [403]

    assert archivo.obtener(0, 3) == producto[:4]


########################################################################################


class ClienteS3Falso:
    def __init__(self, contenido: bytes, *, negar: bool = False) -> None:
        self.contenido: bytes = contenido
        self.negar: bool = negar

    def head_object(self, **kwargs: str) -> dict:
        if self.negar:
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "HeadObject")

        return {"ContentLength": len(self.contenido)}

    def get_object(self, **kwargs: str) -> dict:
        inicio, fin = (
            int(v) for v in kwargs["Range"].removeprefix("bytes=").split("-")
        )

        return {"Body": BytesIO(self.contenido[inicio : fin + 1])}


class CredencialesFalsas(CredencialesS3):
    def __init__(self, cliente: ClienteS3Falso) -> None:
        super().__init__(Session())

        self.falso: ClienteS3Falso = cliente

    def cliente(self, *, forzar: bool = False) -> object:
        return self.falso


def test_s3_reads_ranges_directly(producto: bytes) -> None:
    archivo = ArchivoS3(
        "s3://nisar-cubeta/L2/producto.h5", CredencialesFalsas(ClienteS3Falso(producto))
    )

    assert archivo.cubeta == "nisar-cubeta"
    assert archivo.llave == "L2/producto.h5"
    assert archivo.tamano == len(producto)
    assert archivo.read(8) == producto[:8]


def test_s3_access_outside_the_region_is_denied(producto: bytes) -> None:
    with raises(AccesoDenegadoError):
        ArchivoS3(
            "s3://c/k.h5", CredencialesFalsas(ClienteS3Falso(producto, negar=True))
        )


def test_s3_credentials_are_fetched_and_renewed(monkeypatch: MonkeyPatch) -> None:
    expira = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    datos = {
        "accessKeyId": "a",
        "expiration": expira,
        "secretAccessKey": "b",
        "sessionToken": "c",
    }

    sesion = Session()

    llamadas: list[int] = []

    def obtener(url: str, **kwargs: object) -> Response:
        llamadas.append(1)

        r = respuesta(200)
        r._content = dumps(datos).encode()  # ruff: ignore[private-member-access]

        return r

    monkeypatch.setattr(sesion, "get", obtener)

    credenciales = CredencialesS3(sesion)

    primero = credenciales.cliente()

    assert credenciales.cliente() is primero
    assert len(llamadas) == 1

    credenciales.cliente(forzar=True)

    assert len(llamadas) == 2

    monkeypatch.setattr(sesion, "get", lambda url, **kwargs: respuesta(401))

    with raises(AccesoDenegadoError):
        credenciales.cliente(forzar=True)


def test_access_mode_depends_on_the_aws_region(monkeypatch: MonkeyPatch) -> None:
    assert usar_s3("s3")
    assert not usar_s3("https")

    monkeypatch.setattr(lectura, "region_aws", lambda: "us-west-2")

    assert usar_s3("auto")

    monkeypatch.setattr(lectura, "region_aws", lambda: "eu-west-1")

    assert not usar_s3("auto")


def test_region_lookup_outside_aws_is_none(monkeypatch: MonkeyPatch) -> None:
    def fallar(*args: object, **kwargs: object) -> Response:
        raise RequestException

    monkeypatch.setattr(lectura, "peticion_put", fallar)

    assert region_aws() is None

    monkeypatch.setattr(lectura, "peticion_put", lambda *a, **k: respuesta(200, b"tok"))
    monkeypatch.setattr(
        lectura, "peticion_get", lambda *a, **k: respuesta(200, b"us-west-2 ")
    )

    assert region_aws() == "us-west-2"

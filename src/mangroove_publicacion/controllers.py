from http import HTTPStatus

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse
from dmr import Body, HeaderSpec, Path, ResponseSpec, validate

from api_core.controllers.base import BaseController
from api_core.controllers.components import StrictQuery
from api_core.controllers.endpoints import ModelOperationIdEndpoint
from api_core.controllers.mixins import PublicControllerMixin, StrictThrottlingMixin
from api_core.controllers.serializers import CustomPydanticFastSerializer
from api_exceptions.errors import ApiError
from api_exceptions.schemas import ApiErrorResponse
from mangroove_publicacion import consultas
from mangroove_publicacion.contrato import hipotesis, metodo, resumen
from mangroove_publicacion.schemas import (
    CapaPath,
    CeldaPath,
    EstanquesQuery,
    ExploracionPost,
    FechaCapaPath,
    PuntoQuery,
    RegionPath,
    ResumenQuery,
    VersionPath,
)

########################################################################################

CACHE_SPEC: dict[str, HeaderSpec] = {
    "Cache-Control": HeaderSpec(),
    "ETag": HeaderSpec(required=False),
}

GONE_SPEC: ResponseSpec = ResponseSpec(
    return_type=ApiErrorResponse.from_exc(consultas.RetiradaError),
    status_code=HTTPStatus.GONE,
)

NO_MODIFICADO_SPEC: ResponseSpec = ResponseSpec(
    return_type=None,
    headers=CACHE_SPEC,
    status_code=HTTPStatus.NOT_MODIFIED,
)

REDIRECCION_SPEC: dict[str, HeaderSpec] = {
    "Cache-Control": HeaderSpec(),
    "Location": HeaderSpec(),
}

########################################################################################


def datos_spec(tipo: type) -> tuple[ResponseSpec, ...]:
    return (
        ResponseSpec(return_type=tipo, headers=CACHE_SPEC, status_code=HTTPStatus.OK),
        NO_MODIFICADO_SPEC,
        GONE_SPEC,
    )


def redireccion_spec(estado: HTTPStatus) -> tuple[ResponseSpec, ...]:
    return (
        ResponseSpec(return_type=None, headers=REDIRECCION_SPEC, status_code=estado),
        GONE_SPEC,
    )


class PublicoController(
    PublicControllerMixin,
    BaseController[CustomPydanticFastSerializer],
):
    endpoint_cls = ModelOperationIdEndpoint

    def cacheable(
        self, datos: object, etiqueta: str, cache_control: str
    ) -> HttpResponse:
        encabezados: dict[str, str] = {"Cache-Control": cache_control, "ETag": etiqueta}

        if self.request.headers.get("If-None-Match") == etiqueta:
            return self.to_response(
                None, headers=encabezados, status_code=HTTPStatus.NOT_MODIFIED
            )

        return self.to_response(datos, headers=encabezados, status_code=HTTPStatus.OK)

    def redirigir(
        self, destino: str, estado: HTTPStatus, cache_control: str
    ) -> HttpResponse:
        return self.to_response(
            None,
            headers={"Cache-Control": cache_control, "Location": destino},
            status_code=estado,
        )

    def de_version(
        self, datos: object, ruta: VersionPath, *extra: object
    ) -> HttpResponse:
        return self.cacheable(
            datos,
            consultas.etiqueta(ruta.region, ruta.version, self.request.path, *extra),
            consultas.INMUTABLE,
        )


########################################################################################


class RegionListController(PublicoController):
    @validate(*datos_spec(list[dict]))
    async def get(self) -> HttpResponse:
        datos: list[dict] = await sync_to_async(consultas.regiones)()

        return self.cacheable(datos, consultas.etiqueta(datos), consultas.BREVE)


class ManifiestoVigenteController(PublicoController):
    @validate(*redireccion_spec(HTTPStatus.TEMPORARY_REDIRECT))
    async def get(self, parsed_path: Path[RegionPath]) -> HttpResponse:
        corrida = await sync_to_async(consultas.vigente)(parsed_path.region)

        return self.redirigir(
            f"/regiones/{parsed_path.region}/versiones/{corrida.version}/manifest/",
            HTTPStatus.TEMPORARY_REDIRECT,
            consultas.BREVE,
        )


class ManifiestoController(PublicoController):
    @validate(*datos_spec(dict))
    async def get(self, parsed_path: Path[VersionPath]) -> HttpResponse:
        datos: dict = await sync_to_async(consultas.manifiesto_de)(
            parsed_path.region,
            parsed_path.version,
        )

        return self.de_version(datos, parsed_path)


class CapaFechaController(PublicoController):
    @validate(*redireccion_spec(HTTPStatus.FOUND))
    async def get(self, parsed_path: Path[FechaCapaPath]) -> HttpResponse:
        destino: str = await sync_to_async(consultas.url_capa)(
            parsed_path.region,
            parsed_path.version,
            parsed_path.capa,
            parsed_path.fecha,
        )

        return self.redirigir(destino, HTTPStatus.FOUND, consultas.INMUTABLE)


class CapaController(PublicoController):
    @validate(*redireccion_spec(HTTPStatus.FOUND))
    async def get(self, parsed_path: Path[CapaPath]) -> HttpResponse:
        destino: str = await sync_to_async(consultas.url_capa)(
            parsed_path.region,
            parsed_path.version,
            parsed_path.capa,
        )

        return self.redirigir(destino, HTTPStatus.FOUND, consultas.INMUTABLE)


class CeldaController(PublicoController):
    @validate(*datos_spec(dict))
    async def get(self, parsed_path: Path[CeldaPath]) -> HttpResponse:
        datos: dict = await sync_to_async(consultas.celda_por_codigo)(
            parsed_path.region,
            parsed_path.version,
            parsed_path.celda,
        )

        return self.de_version(datos, parsed_path)


class CeldaPuntoController(PublicoController):
    @validate(*datos_spec(dict))
    async def get(
        self,
        parsed_path: Path[VersionPath],
        parsed_query: StrictQuery[PuntoQuery],
    ) -> HttpResponse:
        datos: dict = await sync_to_async(consultas.celda_por_punto)(
            parsed_path.region,
            parsed_path.version,
            parsed_query.lon,
            parsed_query.lat,
        )

        return self.de_version(datos, parsed_path, datos["id"])


class ResumenController(PublicoController):
    @validate(
        *datos_spec(dict),
        ResponseSpec(
            return_type=None, headers=REDIRECCION_SPEC, status_code=HTTPStatus.FOUND
        ),
    )
    async def get(
        self,
        parsed_path: Path[VersionPath],
        parsed_query: StrictQuery[ResumenQuery],
    ) -> HttpResponse:
        if parsed_query.formato == "csv":
            destino: str = await sync_to_async(consultas.url_resumen_csv)(
                parsed_path.region,
                parsed_path.version,
            )

            return self.redirigir(destino, HTTPStatus.FOUND, consultas.INMUTABLE)

        corrida = await sync_to_async(consultas.publicada)(
            parsed_path.region, parsed_path.version
        )

        datos: dict = await sync_to_async(resumen)(corrida)

        return self.de_version(datos, parsed_path)


class EstanquesController(PublicoController):
    @validate(*datos_spec(list[dict]))
    async def get(
        self,
        parsed_path: Path[VersionPath],
        parsed_query: StrictQuery[EstanquesQuery],
    ) -> HttpResponse:
        datos: list[dict] = await sync_to_async(consultas.estanques_de)(
            parsed_path.region,
            parsed_path.version,
            clase=parsed_query.clase,
            orden=parsed_query.orden,
        )

        return self.de_version(
            datos, parsed_path, parsed_query.clase, parsed_query.orden
        )


class HipotesisController(PublicoController):
    @validate(*datos_spec(list[dict]))
    async def get(self, parsed_path: Path[VersionPath]) -> HttpResponse:
        corrida = await sync_to_async(consultas.publicada)(
            parsed_path.region, parsed_path.version
        )

        return self.de_version(await sync_to_async(hipotesis)(corrida), parsed_path)


class MetodoController(PublicoController):
    @validate(*datos_spec(dict))
    async def get(self, parsed_path: Path[VersionPath]) -> HttpResponse:
        corrida = await sync_to_async(consultas.publicada)(
            parsed_path.region, parsed_path.version
        )

        return self.de_version(await sync_to_async(metodo)(corrida), parsed_path)


class DescargasController(PublicoController):
    @validate(*datos_spec(list[dict]))
    async def get(self, parsed_path: Path[VersionPath]) -> HttpResponse:
        datos: list[dict] = await sync_to_async(consultas.descargas)(
            parsed_path.region,
            parsed_path.version,
        )

        return self.de_version(datos, parsed_path)


class ExploracionController(StrictThrottlingMixin, PublicoController):
    @validate(
        ResponseSpec(return_type=dict, status_code=HTTPStatus.OK),
        GONE_SPEC,
    )
    async def post(
        self,
        parsed_body: Body[ExploracionPost],
        parsed_path: Path[VersionPath],
    ) -> HttpResponse:
        datos: dict = await sync_to_async(consultas.explorar)(
            parsed_path.region,
            parsed_path.version,
            parsed_body.cambios(),
        )

        return self.to_response(datos, status_code=HTTPStatus.OK)


########################################################################################


def capa_exploracion(
    _request: HttpRequest,
    huella: str,
    **_ruta: str,
) -> HttpResponse:
    try:
        contenido: bytes = consultas.png_exploracion(huella)
    except ApiError:
        return HttpResponse(status=HTTPStatus.NOT_FOUND)

    return HttpResponse(
        contenido,
        content_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )

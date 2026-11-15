from typing import TYPE_CHECKING

from dmr.routing import Router, external_path, path

from mangroove_publicacion.controllers import (
    CapaController,
    CapaFechaController,
    CeldaController,
    CeldaPuntoController,
    DescargasController,
    EstanquesController,
    ExploracionController,
    HipotesisController,
    ManifiestoController,
    ManifiestoVigenteController,
    MetodoController,
    RegionListController,
    RelatoController,
    ResumenController,
    capa_exploracion,
)

if TYPE_CHECKING:
    from typing import Final

########################################################################################

VERSION: str = "regiones/<str:region>/versiones/<str:version>"

router: Final[Router] = Router(
    prefix="",
    tags=["mangroove"],
    urls=[
        path("regiones/", RegionListController.as_view(), name="regiones"),
        path(
            "regiones/<str:region>/manifest/",
            ManifiestoVigenteController.as_view(),
            name="regiones-manifest-vigente",
        ),
        path(
            f"{VERSION}/manifest/",
            ManifiestoController.as_view(),
            name="regiones-manifest",
        ),
        path(
            f"{VERSION}/fechas/<str:fecha>/capas/<str:capa>/",
            CapaFechaController.as_view(),
            name="regiones-capa-fecha",
        ),
        path(
            f"{VERSION}/capas/<str:capa>/",
            CapaController.as_view(),
            name="regiones-capa",
        ),
        path(
            f"{VERSION}/celdas/",
            CeldaPuntoController.as_view(),
            name="regiones-celda-punto",
        ),
        path(
            f"{VERSION}/celdas/<str:celda>/",
            CeldaController.as_view(),
            name="regiones-celda",
        ),
        path(
            f"{VERSION}/resumen/", ResumenController.as_view(), name="regiones-resumen"
        ),
        path(
            f"{VERSION}/estanques/",
            EstanquesController.as_view(),
            name="regiones-estanques",
        ),
        path(
            f"{VERSION}/hipotesis/",
            HipotesisController.as_view(),
            name="regiones-hipotesis",
        ),
        path(f"{VERSION}/metodo/", MetodoController.as_view(), name="regiones-metodo"),
        path(
            f"{VERSION}/descargas/",
            DescargasController.as_view(),
            name="regiones-descargas",
        ),
        path(f"{VERSION}/relato/", RelatoController.as_view(), name="regiones-relato"),
        path(
            f"{VERSION}/exploraciones/",
            ExploracionController.as_view(),
            name="regiones-exploraciones",
        ),
        external_path(
            f"{VERSION}/exploraciones/<str:huella>/capas/desconexion/",
            capa_exploracion,
            name="regiones-exploracion-capa",
            openapi=None,
        ),
    ],
)

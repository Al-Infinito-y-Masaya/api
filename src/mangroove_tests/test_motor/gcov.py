from pathlib import Path

from h5py import File
from numpy import arange, bytes_, float32, full, int32, linspace, uint8, uint32

from mangroove_motor.grilla import Grilla

########################################################################################

GRANULO: str = (
    "NISAR_L2_PR_GCOV_034_033_A_008_4005_DHDH_A_20261026T112221_20261026T112255_"
    "P05036_N_F_J_001"
)

PIXEL_M: float = 20.0


def grilla_region() -> Grilla:
    return Grilla(
        epsg=32616, x0=402_000.0, y0=1_448_000.0, celda_m=100.0, ancho=10, alto=8
    )


def escribir_gcov(  # ruff: ignore[too-many-arguments]
    ruta: Path,
    *,
    hh: float = 0.05,
    hv: float = 0.01,
    con_hv: bool = True,
    incidencia_3d: bool = True,
    x0: float = 400_000.0,
    y0: float = 1_450_000.0,
) -> Path:
    filas, columnas = 300, 400

    with File(ruta, "w") as h5:
        grupo = h5.create_group("science/LSAR/GCOV/grids/frequencyA")

        grupo.create_dataset(
            "HHHH", chunks=(64, 64), data=full((filas, columnas), hh, dtype=float32)
        )

        if con_hv:
            grupo.create_dataset(
                "HVHV", chunks=(64, 64), data=full((filas, columnas), hv, dtype=float32)
            )

        mascara = full((filas, columnas), 1, dtype=uint8)
        mascara[:, :10] = 255

        grupo.create_dataset("mask", chunks=(64, 64), data=mascara)
        grupo.create_dataset(
            "xCoordinates", data=x0 + PIXEL_M * (arange(columnas) + 0.5)
        )
        grupo.create_dataset("yCoordinates", data=y0 - PIXEL_M * (arange(filas) + 0.5))

        proyeccion = grupo.create_dataset("projection", data=uint32(32616))
        proyeccion.attrs["epsg_code"] = int32(32616)

        identificacion = h5.create_group("science/LSAR/identification")
        identificacion.create_dataset(
            "zeroDopplerStartTime", data=bytes_("2026-10-26T11:22:21.0")
        )
        identificacion.create_dataset("orbitPassDirection", data=bytes_("Ascending"))

        radar = h5.create_group("science/LSAR/GCOV/metadata/radarGrid")

        if incidencia_3d:
            radar.create_dataset("xCoordinates", data=x0 + 1000.0 * arange(10))
            radar.create_dataset("yCoordinates", data=y0 - 1000.0 * arange(10))
            radar.create_dataset("heightAboveEllipsoid", data=linspace(-500, 1500, 5))
            radar.create_dataset(
                "projection",
                data=uint32(32616),
            ).attrs["epsg_code"] = int32(32616)
            cubo = full((5, 10, 10), 41.0, dtype=float32)
            cubo[1] = 35.5
            radar.create_dataset("incidenceAngle", data=cubo)
        else:
            radar.create_dataset("incidenceAngle", data=float32(40.0))

    return ruta

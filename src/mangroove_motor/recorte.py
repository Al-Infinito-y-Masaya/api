from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from re import compile as compilar
from typing import TYPE_CHECKING

from h5py import Dataset, File, Group
from numpy import (
    abs as np_abs,
    argmin,
    array,
    asarray,
    bytes_,
    float32,
    int32,
    isfinite,
    nan,
    ndarray,
    uint8,
    uint32,
    where,
)
from pyproj import Transformer

if TYPE_CHECKING:
    from mangroove_motor.grilla import Grilla
    from mangroove_motor.lectura import ArchivoRemoto, Avance
    from mangroove_motor.types import Arreglo

########################################################################################

PATRON_GRANULO = compilar(
    r"^NISAR_L2_(?P<proceso>[A-Z]{2})_GCOV_(?P<ciclo>\d{3})_(?P<track>\d{3})_"
    r"(?P<orbita>[AD])_(?P<frame>\d{3})_(?P<modo>\d{4})_(?P<polarizaciones>[A-Z]{4})_"
    r"(?P<lado>[A-Z])_(?P<inicio>\d{8}T\d{6})_(?P<fin>\d{8}T\d{6})_"
    r"(?P<crid>P\d{5})_(?P<fuente>[A-Z])_(?P<cobertura>[A-Z])_(?P<sistema>[A-Z])_"
    r"(?P<contador>\d{3})",
)

FORMATO_INSTANTE: str = "%Y%m%dT%H%M%S"

RAIZ: str = "science/LSAR"
GRUPO_GRILLA: str = f"{RAIZ}/GCOV/grids"
GRUPO_IDENTIFICACION: str = f"{RAIZ}/identification"
GRUPO_RADAR: str = f"{RAIZ}/GCOV/metadata/radarGrid"

FRECUENCIA_PREFERIDA: str = "frequencyA"

########################################################################################


class ProductoInvalidoError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MetadatosGranulo:
    granulo: str
    ciclo: int
    track: int
    frame: int
    orbita: str
    polarizaciones: str
    crid: str
    inicio: datetime
    fin: datetime


@dataclass(frozen=True, slots=True)
class Ventana:
    filas: tuple[int, int]
    columnas: tuple[int, int]


@dataclass(frozen=True, slots=True)
class Recorte:
    hh: Arreglo
    hv: Arreglo
    mascara: Arreglo | None
    xs: Arreglo
    ys: Arreglo
    epsg: int
    frecuencia: str
    incidencia: float | None
    inicio: str
    orbita: str
    granulo: str
    ventana: Ventana

    @property
    def pixel_m(self) -> float:
        if len(self.xs) < 2:  # ruff: ignore[magic-value-comparison]
            return float("nan")

        return float(abs(self.xs[1] - self.xs[0]))


@dataclass(frozen=True, slots=True)
class ArchivoEscrito:
    ruta: Path
    sha256: str
    bytes: int


########################################################################################


def parsear_granulo(nombre: str) -> MetadatosGranulo:
    base: str = Path(nombre.split("?", maxsplit=1)[0]).name.removesuffix(".h5")

    coincidencia = PATRON_GRANULO.match(base)

    if coincidencia is None:
        raise ProductoInvalidoError(f"{base!r} no es un gránulo NISAR L2 GCOV.")

    def instante(valor: str) -> datetime:
        return datetime.strptime(valor, FORMATO_INSTANTE).replace(tzinfo=UTC)

    return MetadatosGranulo(
        granulo=base[: coincidencia.end()],
        ciclo=int(coincidencia["ciclo"]),
        track=int(coincidencia["track"]),
        frame=int(coincidencia["frame"]),
        orbita="asc" if coincidencia["orbita"] == "A" else "desc",
        polarizaciones=coincidencia["polarizaciones"],
        crid=coincidencia["crid"],
        inicio=instante(coincidencia["inicio"]),
        fin=instante(coincidencia["fin"]),
    )


########################################################################################


def buscar(h5: File, nombre: str, preferir: str | None = None) -> str | None:
    encontrados: list[str] = []

    def visitar(ruta: str, objeto: object) -> None:
        if ruta.rsplit("/", 1)[-1] == nombre and isinstance(objeto, Dataset):
            encontrados.append(ruta)

    h5.visititems(visitar)

    if preferir is not None:
        preferidos: list[str] = [r for r in encontrados if preferir in r]

        if preferidos:
            return preferidos[0]

    return encontrados[0] if encontrados else None


def texto(h5: File, nombre: str) -> str | None:
    ruta: str | None = buscar(h5, nombre)

    if ruta is None:
        return None

    valor = h5[ruta][()]

    if isinstance(valor, ndarray):
        valor = valor.flat[0]

    return valor.decode() if isinstance(valor, bytes | bytes_) else str(valor)


def epsg_de(dataset: Dataset) -> int | None:
    for atributo in ("epsg_code", "epsg"):
        if atributo in dataset.attrs:
            valor: int = int(asarray(dataset.attrs[atributo]).flat[0])

            return valor or None

    try:
        valor = int(asarray(dataset[()]).flat[0])
    except TypeError, ValueError:
        return None

    return valor or None


def coordenadas_de(h5: File, ruta: str) -> tuple[Arreglo, Arreglo, str]:
    partes: list[str] = ruta.split("/")

    for k in range(len(partes) - 1, 0, -1):
        grupo: str = "/".join(partes[:k])

        nodo = h5.get(grupo)

        if (
            isinstance(nodo, Group)
            and "xCoordinates" in nodo
            and "yCoordinates" in nodo
        ):
            return nodo["xCoordinates"][()], nodo["yCoordinates"][()], grupo

    raise ProductoInvalidoError(f"No hay xCoordinates/yCoordinates para {ruta}.")


########################################################################################


def indice_ventana(
    xs: Arreglo,
    ys: Arreglo,
    epsg: int,
    grilla: Grilla,
    margen_m: float,
) -> Ventana | None:
    oeste, sur, este, norte = grilla.limites()

    gx: Arreglo = array([oeste - margen_m, este + margen_m] * 2)
    gy: Arreglo = array([norte + margen_m] * 2 + [sur - margen_m] * 2)

    if epsg != grilla.epsg:
        gx, gy = Transformer.from_crs(
            grilla.crs, f"EPSG:{epsg}", always_xy=True
        ).transform(
            gx,
            gy,
        )

        gx, gy = asarray(gx), asarray(gy)

    columnas: Arreglo = where((xs >= gx.min()) & (xs <= gx.max()))[0]
    filas: Arreglo = where((ys >= gy.min()) & (ys <= gy.max()))[0]

    if columnas.size == 0 or filas.size == 0:
        return None

    return Ventana(
        filas=(int(filas.min()), int(filas.max()) + 1),
        columnas=(int(columnas.min()), int(columnas.max()) + 1),
    )


def chunks_ventana(dataset: Dataset, ventana: Ventana) -> list[tuple[int, int]]:
    if dataset.chunks is None or dataset.ndim != 2:  # ruff: ignore[magic-value-comparison]
        return []

    cy, cx = dataset.chunks
    r0, r1 = ventana.filas
    c0, c1 = ventana.columnas

    salida: list[tuple[int, int]] = []

    for fila in range(r0 // cy, (r1 - 1) // cy + 1):
        for columna in range(c0 // cx, (c1 - 1) // cx + 1):
            info = dataset.id.get_chunk_info_by_coord((fila * cy, columna * cx))

            if info.byte_offset is not None and info.size:
                salida.append((int(info.byte_offset), int(info.size)))

    return salida


def bytes_ventana(dataset: Dataset, ventana: Ventana) -> int:
    chunks: list[tuple[int, int]] = chunks_ventana(dataset, ventana)

    if chunks:
        return sum(n for _, n in chunks)

    r0, r1 = ventana.filas

    return (r1 - r0) * dataset.shape[1] * dataset.dtype.itemsize


def incidencia_media(  # ruff: ignore[too-many-locals]
    h5: File,
    grilla: Grilla,
) -> float | None:
    ruta: str | None = buscar(h5, "incidenceAngle")

    if ruta is None:
        return None

    dataset: Dataset = h5[ruta]

    if dataset.ndim == 0:
        valor: float = float(dataset[()])

        return round(valor, 2) if isfinite(valor) else None

    try:
        xs, ys, grupo = coordenadas_de(h5, ruta)
    except ProductoInvalidoError:
        return None

    proyeccion: str | None = buscar(h5, "projection", preferir=grupo)

    epsg: int | None = epsg_de(h5[proyeccion]) if proyeccion else None

    ventana: Ventana | None = indice_ventana(
        xs, ys, epsg or grilla.epsg, grilla, 1000.0
    )

    if ventana is None:
        return None

    r0, r1 = ventana.filas
    c0, c1 = ventana.columnas

    if dataset.ndim == 3:  # ruff: ignore[magic-value-comparison]
        alturas: str = f"{grupo}/heightAboveEllipsoid"

        capa: int = (
            int(argmin(np_abs(h5[alturas][()])))
            if alturas in h5
            else dataset.shape[0] // 2
        )

        bloque: Arreglo = dataset[capa, r0:r1, c0:c1]
    else:
        bloque = dataset[r0:r1, c0:c1]

    finitos: Arreglo = asarray(bloque, dtype=float32)

    finitos = finitos[isfinite(finitos)]

    if finitos.size == 0:
        return None

    return round(float(finitos.mean()), 2)


########################################################################################


def leer_ventana(  # ruff: ignore[too-many-arguments, too-many-locals]
    h5: File,
    grilla: Grilla,
    *,
    margen_m: float,
    granulo: str,
    archivo: ArchivoRemoto | None = None,
    avance: Avance | None = None,
) -> Recorte | None:
    ruta_hh: str | None = buscar(h5, "HHHH", preferir=FRECUENCIA_PREFERIDA)

    if ruta_hh is None:
        raise ProductoInvalidoError("El producto no trae HHHH.")

    grupo: str = ruta_hh.rsplit("/", 1)[0]

    ruta_hv: str = f"{grupo}/HVHV"

    if ruta_hv not in h5:
        raise ProductoInvalidoError("El producto no trae HVHV.")

    ruta_mascara: str | None = f"{grupo}/mask" if f"{grupo}/mask" in h5 else None

    xs: Arreglo = h5[f"{grupo}/xCoordinates"][()]
    ys: Arreglo = h5[f"{grupo}/yCoordinates"][()]

    proyeccion: str | None = (
        f"{grupo}/projection"
        if f"{grupo}/projection" in h5
        else buscar(h5, "projection")
    )

    epsg: int | None = epsg_de(h5[proyeccion]) if proyeccion else None

    if epsg is None:
        raise ProductoInvalidoError("El producto no declara un EPSG legible.")

    ventana: Ventana | None = indice_ventana(xs, ys, epsg, grilla, margen_m)

    if ventana is None:
        return None

    rutas: list[str] = [ruta_hh, ruta_hv, *([ruta_mascara] if ruta_mascara else [])]

    if archivo is not None:
        rangos: list[tuple[int, int]] = []

        for ruta in rutas:
            rangos += chunks_ventana(h5[ruta], ventana)

        if rangos:
            archivo.precargar(rangos, avance)

    r0, r1 = ventana.filas
    c0, c1 = ventana.columnas

    recorte: Recorte = Recorte(
        hh=asarray(h5[ruta_hh][r0:r1, c0:c1], dtype=float32),
        hv=asarray(h5[ruta_hv][r0:r1, c0:c1], dtype=float32),
        mascara=(
            asarray(h5[ruta_mascara][r0:r1, c0:c1], dtype=uint8)
            if ruta_mascara
            else None
        ),
        xs=asarray(xs[c0:c1]),
        ys=asarray(ys[r0:r1]),
        epsg=epsg,
        frecuencia=grupo.rsplit("/", 1)[-1],
        incidencia=incidencia_media(h5, grilla),
        inicio=texto(h5, "zeroDopplerStartTime") or "",
        orbita=texto(h5, "orbitPassDirection") or "",
        granulo=granulo,
        ventana=ventana,
    )

    if archivo is not None:
        archivo.limpiar_previos()

    return recorte


########################################################################################


def suma_sha256(ruta: Path) -> str:
    resumen = sha256()

    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b""):
            resumen.update(bloque)

    return resumen.hexdigest()


def escribir_recorte(ruta: Path, recorte: Recorte, fuente: str) -> ArchivoEscrito:
    ruta.parent.mkdir(parents=True, exist_ok=True)

    parcial: Path = ruta.with_name(ruta.name + ".part")

    with File(parcial, "w") as salida:
        grupo: Group = salida.create_group(f"{GRUPO_GRILLA}/{recorte.frecuencia}")

        capas: dict[str, Arreglo] = {"HHHH": recorte.hh, "HVHV": recorte.hv}

        if recorte.mascara is not None:
            capas["mask"] = recorte.mascara

        for nombre, valores in capas.items():
            grupo.create_dataset(
                nombre,
                chunks=True,
                compression="gzip",
                compression_opts=4,
                data=valores,
                shuffle=True,
            )

        grupo.create_dataset("xCoordinates", data=recorte.xs)
        grupo.create_dataset("yCoordinates", data=recorte.ys)

        proyeccion: Dataset = grupo.create_dataset(
            "projection", data=uint32(recorte.epsg)
        )
        proyeccion.attrs["epsg_code"] = int32(recorte.epsg)

        identificacion: Group = salida.create_group(GRUPO_IDENTIFICACION)

        for nombre, valor in (
            ("zeroDopplerStartTime", recorte.inicio),
            ("orbitPassDirection", recorte.orbita),
            ("granuleId", recorte.granulo),
        ):
            identificacion.create_dataset(nombre, data=bytes_(valor))

        salida.create_group(GRUPO_RADAR).create_dataset(
            "incidenceAngle",
            data=float32(nan if recorte.incidencia is None else recorte.incidencia),
        )

        salida.attrs["fuente"] = fuente
        salida.attrs["ventana_filas_columnas"] = [
            *recorte.ventana.filas,
            *recorte.ventana.columnas,
        ]

    Path(parcial).replace(ruta)

    return ArchivoEscrito(
        ruta=ruta, sha256=suma_sha256(ruta), bytes=ruta.stat().st_size
    )


def leer_recorte(ruta: Path) -> Recorte:
    with File(ruta, "r") as h5:
        ruta_hh: str | None = buscar(h5, "HHHH", preferir=FRECUENCIA_PREFERIDA)

        if ruta_hh is None:
            raise ProductoInvalidoError(f"El recorte {ruta.name} no trae HHHH.")

        grupo: str = ruta_hh.rsplit("/", 1)[0]

        mascara: Arreglo | None = (
            asarray(h5[f"{grupo}/mask"][()], dtype=uint8)
            if f"{grupo}/mask" in h5
            else None
        )

        epsg: int | None = epsg_de(h5[f"{grupo}/projection"])

        if epsg is None:
            raise ProductoInvalidoError(f"El recorte {ruta.name} no declara un EPSG.")

        incidencia: float = float(h5[f"{GRUPO_RADAR}/incidenceAngle"][()])

        filas_columnas: list[int] = [
            int(v) for v in h5.attrs.get("ventana_filas_columnas", [0, 0, 0, 0])
        ]

        return Recorte(
            hh=asarray(h5[ruta_hh][()], dtype=float32),
            hv=asarray(h5[f"{grupo}/HVHV"][()], dtype=float32),
            mascara=mascara,
            xs=asarray(h5[f"{grupo}/xCoordinates"][()]),
            ys=asarray(h5[f"{grupo}/yCoordinates"][()]),
            epsg=epsg,
            frecuencia=grupo.rsplit("/", 1)[-1],
            incidencia=round(incidencia, 2) if isfinite(incidencia) else None,
            inicio=texto(h5, "zeroDopplerStartTime") or "",
            orbita=texto(h5, "orbitPassDirection") or "",
            granulo=texto(h5, "granuleId") or ruta.stem,
            ventana=Ventana(
                filas=(filas_columnas[0], filas_columnas[1]),
                columnas=(filas_columnas[2], filas_columnas[3]),
            ),
        )

from django.db.models import TextChoices

########################################################################################


class TipoArtefacto(TextChoices):
    RGB = "rgb"
    CLASES = "clases"
    IF_ALTA = "if_alta"
    IF = "if"
    DESCONEXION = "desconexion"
    P_ERROR = "p_error"
    CAMBIO = "cambio"
    GEOTIFF_IF_ALTA = "geotiff_if_alta"
    GEOTIFF_IF = "geotiff_if"
    GEOTIFF_DESCONEXION = "geotiff_desconexion"
    GEOTIFF_P_ERROR = "geotiff_p_error"
    GEOTIFF_CAMBIO = "geotiff_cambio"
    GEOTIFF_CLASE_TIPICA = "geotiff_clase_tipica"
    RESUMEN_CSV = "resumen_csv"
    ESTANQUES = "estanques"
    METADATOS = "metadatos"
    MANIFIESTO = "manifiesto"
    RESUMEN = "resumen"


class FormatoArtefacto(TextChoices):
    PNG = "png"
    TIF = "tif"
    CSV = "csv"
    JSON = "json"
    GEOJSON = "geojson"


POR_FECHA: tuple[str, ...] = (TipoArtefacto.RGB, TipoArtefacto.CLASES)

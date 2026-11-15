from django.db.models import TextChoices

########################################################################################


class TipoInsumo(TextChoices):
    MANGLAR = "manglar"
    ELEVACION = "elevacion"
    EXCLUSION = "exclusion"
    BARRERAS = "barreras"
    ESTANQUES = "estanques"
    PAISES = "paises"
    AREAS_PROTEGIDAS = "areas_protegidas"
    OPTICO = "optico"
    BANDA_C = "banda_c"


class FormatoInsumo(TextChoices):
    RASTER = "raster"
    VECTOR = "vector"


class TipoSerie(TextChoices):
    MAREA = "marea"
    LLUVIA = "lluvia"

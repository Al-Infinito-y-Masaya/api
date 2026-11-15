from django.db.models import TextChoices

########################################################################################


class EstadoCorrida(TextChoices):
    PENDIENTE = "pendiente"
    EN_PROCESO = "en_proceso"
    COMPLETADA = "completada"
    FALLIDA = "fallida"
    PUBLICADA = "publicada"
    RETIRADA = "retirada"


class OrbitaCorrida(TextChoices):
    AMBAS = "ambas"
    ASC = "asc"
    DESC = "desc"


class MadurezCorrida(TextChoices):
    PROVISIONAL = "provisional"
    VALIDADO = "validado"


class NivelMareaCorrida(TextChoices):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"
    DESCONOCIDA = "desconocida"


class PruebaEstadistica(TextChoices):
    MANN_WHITNEY = "mann_whitney"
    FISHER = "fisher"

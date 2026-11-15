from django.db.models import TextChoices

########################################################################################


class Madurez(TextChoices):
    BETA = "beta"
    PROVISIONAL = "provisional"
    VALIDADO = "validado"


class Orbita(TextChoices):
    ASC = "asc"
    DESC = "desc"


class EstadoRecorte(TextChoices):
    PENDIENTE = "pendiente"
    RECORTADO = "recortado"
    DESCARTADO = "descartado"
    FALLIDO = "fallido"


class OrigenSincronizacion(TextChoices):
    PROGRAMADA = "programada"
    MANUAL = "manual"


class EstadoSincronizacion(TextChoices):
    EN_CURSO = "en_curso"
    COMPLETADA = "completada"
    FALLIDA = "fallida"

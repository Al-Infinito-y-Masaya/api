from datetime import date

from django.core.management.base import CommandError
from django.db.models import Q

from api_auth.models import ApiUser
from mangroove_analisis.models import Corrida
from mangroove_regiones.models import Region

########################################################################################


def region_por_codigo(codigo: str) -> Region:
    region: Region | None = Region.objects.filter(codigo=codigo, is_active=True).first()

    if region is None:
        raise CommandError(f"No hay una región activa con código {codigo!r}.")

    return region


def usuario_por_identificador(identificador: str) -> ApiUser:
    usuario: ApiUser | None = ApiUser.objects.filter(
        Q(email__iexact=identificador) | Q(username=identificador),
        is_active=True,
    ).first()

    if usuario is None:
        raise CommandError(f"No hay una cuenta activa {identificador!r}.")

    return usuario


def corrida_por_id(identificador: str) -> Corrida:
    corrida: Corrida | None = Corrida.objects.filter(id=identificador).first()

    if corrida is None:
        raise CommandError(f"No existe la corrida {identificador}.")

    return corrida


def fecha(texto: str) -> date:
    try:
        return date.fromisoformat(texto)
    except ValueError as e:
        raise CommandError(f"{texto!r} no es una fecha AAAA-MM-DD.") from e

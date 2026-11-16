from http import HTTPStatus

from django.http import HttpResponse
from dmr import ResponseSpec, validate
from health_check import Cache, Database, Storage
from health_check.base import HealthCheckResult

from api_core.controllers.mixins import PublicControllerMixin
from api_core.schemas.health import HealthCheckError, HealthCheckSuccess

from .base import BaseController
from .serializers import CustomPydanticFastSerializer

########################################################################################


class HealthCheckController(
    PublicControllerMixin,
    BaseController[CustomPydanticFastSerializer],
):
    # Docker and Caddy probe this endpoint on a schedule; a 429 would mark a healthy
    # API as down, so the probe is never throttled.
    throttling = None

    @validate(
        ResponseSpec(
            return_type=HealthCheckSuccess,
            status_code=HTTPStatus.OK,
        ),
        ResponseSpec(
            return_type=HealthCheckError,
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        ),
    )
    async def get(self) -> HttpResponse:
        results: list[HealthCheckResult] = [
            await Cache().get_result(),
            await Database().get_result(),
            await Storage().get_result(),
        ]

        code: HTTPStatus = (
            HTTPStatus.SERVICE_UNAVAILABLE
            if any(result.error is not None for result in results)
            else HTTPStatus.OK
        )

        components: dict = {
            result.check.__class__.__name__.lower(): (
                "ok" if result.error is None else result.error.message_type.lower()
            )
            for result in results
        }

        if code == HTTPStatus.OK:
            data = HealthCheckSuccess(components=components)
        else:
            data = HealthCheckError(components=components)

        return self.to_response(raw_data=data, status_code=code)

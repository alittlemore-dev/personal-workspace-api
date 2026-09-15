from unittest.mock import Mock

from dishka import Provider, Scope, provide

from core.resumes.use_cases import ResumesUseCase


class MockResumesProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_resumes_use_case(self) -> ResumesUseCase:
        return Mock(spec=ResumesUseCase)

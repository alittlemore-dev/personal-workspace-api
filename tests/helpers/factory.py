from dataclasses import dataclass
from functools import cached_property

from tests.helpers.factories.api import ApiFactoryHelper
from tests.helpers.factories.core import CoreFactoryHelper
from tests.helpers.factories.database import DatabaseFactoryHelper


@dataclass(kw_only=True, frozen=True)
class FactoryHelper:
    @cached_property
    def core(self) -> CoreFactoryHelper:
        return CoreFactoryHelper()

    @cached_property
    def api(self) -> ApiFactoryHelper:
        return ApiFactoryHelper()

    @cached_property
    def db(self) -> DatabaseFactoryHelper:
        return DatabaseFactoryHelper()

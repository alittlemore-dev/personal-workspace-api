from zoneinfo import ZoneInfo

from sqlalchemy.dialects import postgresql

from infra.postgresql.types import ZoneInfoType


def test_zone_info_column_maps_iana_key_and_domain_object() -> None:
    column_type = ZoneInfoType()
    dialect = postgresql.dialect()

    assert column_type.process_bind_param(ZoneInfo("Asia/Yerevan"), dialect) == "Asia/Yerevan"
    assert column_type.process_result_value("Asia/Yerevan", dialect) == ZoneInfo(
        "Asia/Yerevan",
    )

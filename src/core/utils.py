from datetime import date


def next_month(period: date) -> date:
    months_per_year = 12
    return date(
        period.year + (period.month == months_per_year),
        period.month % months_per_year + 1,
        1,
    )

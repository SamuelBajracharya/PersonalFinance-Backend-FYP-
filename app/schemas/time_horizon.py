from enum import Enum


class TimeHorizon(str, Enum):
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"
    NINETY_DAYS = "90d"
    CALENDAR_MONTH = "calendar_month"

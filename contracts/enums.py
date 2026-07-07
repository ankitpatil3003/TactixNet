from enum import Enum


class AlertLevel(str, Enum):
    CALM = "CALM"
    SUSPICIOUS = "SUSPICIOUS"
    ALERT = "ALERT"
    COMPROMISED = "COMPROMISED"


class RoleEnum(str, Enum):
    FLANK = "flank"
    DISTRACT = "distract"
    STEALTH_COVER = "stealth-cover"
    OVERWATCH = "overwatch"
    BREACH = "breach"

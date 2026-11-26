"""Map SEC SIC codes to a small set of analyst-friendly sectors."""

from __future__ import annotations

# Specific codes first (checked before ranges): the SEC groups most of big tech under
# manufacturing/services ranges that are too coarse to be useful.
_SPECIFIC: dict[int, str] = {
    3570: "Technology Hardware",
    3571: "Technology Hardware",
    3572: "Technology Hardware",
    3576: "Technology Hardware",
    3577: "Technology Hardware",
    3661: "Communications Equipment",
    3663: "Communications Equipment",
    3669: "Communications Equipment",
    3674: "Semiconductors",
    3672: "Semiconductors",
    3825: "Semiconductors",
    7370: "Software & Internet",
    7371: "Software & Internet",
    7372: "Software & Internet",
    7373: "Software & Internet",
    7374: "Software & Internet",
    5961: "Consumer Discretionary",
    3711: "Consumer Discretionary",
    4841: "Communication Services",
    4813: "Communication Services",
    4899: "Communication Services",
    6022: "Banks",
    6021: "Banks",
    6029: "Banks",
    6035: "Banks",
    6036: "Banks",
    6199: "Financial Services",
    6141: "Financial Services",
    6153: "Financial Services",
    6211: "Capital Markets",
    6282: "Capital Markets",
    6200: "Capital Markets",
    6311: "Insurance",
    6331: "Insurance",
    6324: "Insurance",
    6411: "Insurance",
    6770: "Blank Checks",
}

_RANGES: list[tuple[int, int, str]] = [
    (100, 999, "Agriculture"),
    (1000, 1499, "Energy & Mining"),
    (1500, 1799, "Industrials"),
    (2000, 2399, "Consumer Staples"),
    (2800, 2836, "Health Care"),
    (2837, 2999, "Materials"),
    (2400, 3499, "Materials"),
    (3500, 3999, "Industrials"),
    (4000, 4799, "Industrials"),
    (4800, 4899, "Communication Services"),
    (4900, 4999, "Utilities"),
    (5000, 5999, "Consumer Discretionary"),
    (6000, 6199, "Banks"),
    (6200, 6299, "Capital Markets"),
    (6300, 6499, "Insurance"),
    (6500, 6799, "Real Estate"),
    (7000, 7999, "Services"),
    (8000, 8099, "Health Care"),
    (8100, 8999, "Services"),
    (9000, 9999, "Public Administration"),
]


def sector_for_sic(sic: str | int | None) -> str | None:
    if sic in (None, ""):
        return None
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return None
    if code in _SPECIFIC:
        return _SPECIFIC[code]
    for lo, hi, name in _RANGES:
        if lo <= code <= hi:
            return name
    return None

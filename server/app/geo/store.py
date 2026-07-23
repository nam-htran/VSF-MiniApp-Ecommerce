"""Vietnam administrative units — provinces, districts, wards.

A static dataset (63 provinces, three levels) bundled with the server and
served by level, so the MiniApp fetches a short list at each step instead
of shipping the whole ~600 KB tree in its bundle. Read once at import and
indexed into flat lookups; the data never changes at runtime.

Source: kenzouno1/DiaGioiHanhChinhVN. Raw keys are Id/Name/Districts/Wards;
normalised here to {code, name}.
"""

import json
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "vn_admin.json"

with _DATA_PATH.open(encoding="utf-8") as _file:
    _RAW = json.load(_file)

# province_code -> districts, district_code -> wards. Built once.
_PROVINCES: list[dict] = [{"code": p["Id"], "name": p["Name"]} for p in _RAW]
_DISTRICTS: dict[str, list[dict]] = {}
_WARDS: dict[str, list[dict]] = {}

# A few island-district ward entries in the source are malformed (no Id
# or Name — e.g. Huyện Bạch Long Vĩ); skip anything missing either key.
def _units(rows: list[dict]) -> list[dict]:
    return [
        {"code": r["Id"], "name": r["Name"]}
        for r in rows
        if r.get("Id") and r.get("Name")
    ]


for _province in _RAW:
    _DISTRICTS[_province["Id"]] = _units(_province["Districts"])
    for _district in _province["Districts"]:
        _WARDS[_district["Id"]] = _units(_district["Wards"])


def list_provinces() -> list[dict]:
    return _PROVINCES


def list_districts(province_code: str) -> list[dict]:
    return _DISTRICTS.get(province_code, [])


def list_wards(district_code: str) -> list[dict]:
    return _WARDS.get(district_code, [])

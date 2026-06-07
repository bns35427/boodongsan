from __future__ import annotations

import csv
from dataclasses import dataclass, fields
from pathlib import Path


REQUIRED_COLUMNS = {
    "platform",
    "property_type",
    "deal_type",
    "sido",
    "sigungu",
    "eupmyeon_dong",
    "jibun",
    "detail_addr",
    "deposit",
    "monthly_rent",
    "maintenance_fee",
    "floor",
    "total_floor",
    "room_count",
    "bath_count",
    "direction",
    "parking",
    "move_in_date",
    "title",
    "memo",
}


@dataclass(frozen=True)
class Listing:
    source_row: int
    platform: str
    property_type: str
    deal_type: str
    sido: str
    sigungu: str
    eupmyeon_dong: str
    ri: str
    jibun: str
    building_dong: str
    detail_addr: str
    deposit: str
    monthly_rent: str
    maintenance_fee: str
    exclusive_area_m2: str
    supply_area_m2: str
    floor: str
    total_floor: str
    room_count: str
    bath_count: str
    direction: str
    direction_basis: str
    parking: str
    move_in_date: str
    title: str
    memo: str
    option_aircon: str
    option_life: str
    option_security: str
    option_etc: str
    photo_folder: str

    @property
    def display_name(self) -> str:
        address = " ".join(
            part
            for part in (
                self.sido,
                self.sigungu,
                self.eupmyeon_dong,
                self.ri,
                self.jibun,
                self.detail_addr,
            )
            if part
        )
        return f"{self.source_row}행 {address}"


def _clean_row(row: dict[str | None, str | list[str] | None]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized_key = key.strip().lstrip("\ufeff")
        if not normalized_key or normalized_key.lower().startswith("unnamed:"):
            continue
        if isinstance(value, list):
            cleaned[normalized_key] = "|".join(value).strip()
        else:
            cleaned[normalized_key] = (value or "").strip()
    return cleaned


def _validate_listing(listing: Listing) -> None:
    if listing.platform.lower() not in {"aipartner", "이실장"}:
        raise ValueError(f"지원하지 않는 platform: {listing.platform}")
    if listing.property_type.lower() not in {"oneroom", "원룸"}:
        raise ValueError(f"지원하지 않는 property_type: {listing.property_type}")
    if not listing.jibun.split("-", 1)[0].isdigit():
        raise ValueError(f"지번 형식이 올바르지 않습니다: {listing.jibun}")
    if len(listing.title) > 40:
        raise ValueError("title은 이실장 매물특징 제한인 40자를 넘을 수 없습니다.")
    if len(listing.memo) > 1000:
        raise ValueError("memo는 1000자를 넘을 수 없습니다.")


def load_listings(csv_path: Path) -> tuple[list[Listing], list[str]]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        headers = {
            header.strip().lstrip("\ufeff")
            for header in (reader.fieldnames or [])
            if header and header.strip()
        }
        missing = sorted(REQUIRED_COLUMNS - headers)
        if missing:
            raise ValueError(f"CSV 필수 컬럼이 없습니다: {', '.join(missing)}")

        warnings: list[str] = []
        if "exclusive_area_m2" not in headers:
            warnings.append(
                "exclusive_area_m2 컬럼이 없어 supply_area_m2 값을 전용면적에도 사용합니다."
            )
        if "direction_basis" not in headers:
            warnings.append(
                "direction_basis 컬럼이 없어 호환 기본값 '안방'을 사용합니다."
            )
        if "option_etc" not in headers:
            warnings.append("option_etc 컬럼이 없어 기타시설은 선택하지 않습니다.")
        if "building_dong" not in headers:
            warnings.append(
                "building_dong 컬럼이 없어 건축물대장 유형 정보가 없을 때 "
                "일반 건물로 판단합니다."
            )

        listings: list[Listing] = []
        listing_fields = {
            field.name for field in fields(Listing) if field.name != "source_row"
        }
        for source_row, raw_row in enumerate(reader, start=2):
            row = _clean_row(raw_row)
            if not any(row.values()):
                continue
            if not row.get("exclusive_area_m2"):
                row["exclusive_area_m2"] = row.get("supply_area_m2", "")
            if not row.get("supply_area_m2"):
                row["supply_area_m2"] = row.get("exclusive_area_m2", "")
            if not row.get("direction_basis"):
                row["direction_basis"] = "안방"

            values = {name: row.get(name, "") for name in listing_fields}
            listing = Listing(source_row=source_row, **values)
            _validate_listing(listing)
            listings.append(listing)

    if not listings:
        raise ValueError("처리할 CSV 데이터 행이 없습니다.")
    return listings, warnings

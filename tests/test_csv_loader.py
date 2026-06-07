from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from src.aipartner_oneroom import AIPartnerOneRoom
from src.csv_loader import load_listings


class CsvLoaderTest(unittest.TestCase):
    def test_example_csv_loads(self) -> None:
        csv_text = (
            "platform,property_type,deal_type,sido,sigungu,eupmyeon_dong,ri,"
            "jibun,building_dong,detail_addr,deposit,monthly_rent,maintenance_fee,"
            "exclusive_area_m2,supply_area_m2,floor,total_floor,room_count,"
            "bath_count,direction,direction_basis,parking,move_in_date,title,memo,"
            "option_aircon,option_life,option_security,option_etc,photo_folder\n"
            "aipartner,oneroom,monthly,울산,울주군,온산읍,덕신리,1299-18,,"
            "202,300,35,5,26.4,26.4,2,4,1,1,동향,거실,Y,즉시입주,테스트,설명,"
            "TRUE,냉장고,CCTV,베란다,\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.csv"
            path.write_text(csv_text, encoding="utf-8")
            rows, warnings = load_listings(path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(warnings, [])
        self.assertEqual(rows[0].exclusive_area_m2, "26.4")
        self.assertEqual(rows[0].direction_basis, "거실")
        self.assertEqual(rows[0].option_etc, "베란다")

    def test_legacy_empty_index_and_missing_exclusive_area(self) -> None:
        csv_text = (
            ",platform,property_type,deal_type,sido,sigungu,eupmyeon_dong,ri,"
            "jibun,detail_addr,deposit,monthly_rent,maintenance_fee,"
            "supply_area_m2,floor,total_floor,room_count,bath_count,direction,"
            "parking,move_in_date,title,memo,option_aircon,option_life,"
            "option_security,photo_folder\n"
            ",aipartner,oneroom,monthly,울산,울주군,온산읍,덕신리,1299-18,"
            "202,300,35,5,26.4,2,4,1,1,동향,Y,즉시입주,테스트,설명,TRUE,"
            "냉장고,CCTV,\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.csv"
            path.write_text(csv_text, encoding="utf-8")
            rows, warnings = load_listings(path)

        self.assertEqual(rows[0].exclusive_area_m2, "26.4")
        self.assertEqual(rows[0].direction_basis, "안방")
        self.assertEqual(len(warnings), 4)


class ValueMappingTest(unittest.TestCase):
    def test_jibun_split(self) -> None:
        self.assertEqual(
            AIPartnerOneRoom._split_jibun("1299-18"), ("1299", "18")
        )
        self.assertEqual(AIPartnerOneRoom._split_jibun("834"), ("834", ""))

    def test_building_ledger_unit_normalization(self) -> None:
        self.assertEqual(AIPartnerOneRoom._normalize_unit("101"), "101")
        self.assertEqual(AIPartnerOneRoom._normalize_unit("101호"), "101")
        self.assertEqual(AIPartnerOneRoom._normalize_unit(" 101 호 "), "101")
        self.assertEqual(AIPartnerOneRoom._normalize_dong("101동"), "101")
        self.assertEqual(
            AIPartnerOneRoom._normalize_dong("(101동)"), "101"
        )
        self.assertEqual(AIPartnerOneRoom._normalize_floor("2층"), "2")
        self.assertEqual(AIPartnerOneRoom._normalize_floor("-1층"), "-1")

    def test_deal_code(self) -> None:
        self.assertEqual(AIPartnerOneRoom._deal_code("monthly"), "M")
        self.assertEqual(AIPartnerOneRoom._deal_code("월세"), "M")

    def test_dong_address_skips_ri_dropdown(self) -> None:
        csv_text = (
            "platform,property_type,deal_type,sido,sigungu,eupmyeon_dong,ri,"
            "jibun,detail_addr,deposit,monthly_rent,maintenance_fee,"
            "exclusive_area_m2,supply_area_m2,floor,total_floor,room_count,"
            "bath_count,direction,parking,move_in_date,title,memo,"
            "option_aircon,option_life,option_security,photo_folder\n"
            "aipartner,oneroom,monthly,울산,남구,무거동,,345,101,300,35,5,"
            "26.4,26.4,2,4,1,1,동향,Y,즉시입주,테스트,설명,,,,\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dong.csv"
            path.write_text(csv_text, encoding="utf-8")
            rows, _ = load_listings(path)

        listing = replace(rows[0])
        self.assertEqual(
            AIPartnerOneRoom._address_selections(listing),
            [
                ("#naddr1Text", "#naddr1List", "울산"),
                ("#naddr2Text", "#naddr2List", "남구"),
                ("#naddr3Text", "#naddr3List", "무거동"),
            ],
        )
        self.assertEqual(AIPartnerOneRoom._split_jibun(listing.jibun), ("345", ""))


if __name__ == "__main__":
    unittest.main()

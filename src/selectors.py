from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocatorSpec:
    """안정적인 선택자를 우선순위대로 보관한다."""

    css: tuple[str, ...] = ()
    text: tuple[str, ...] = ()
    role: str | None = None
    role_names: tuple[str, ...] = ()


LOGIN_ID = LocatorSpec(
    css=("#member-id", "input[name='member-id']"),
    text=(),
)
LOGIN_PASSWORD = LocatorSpec(
    css=("#member-pw", "input[name='member-pw']"),
    text=(),
)
LOGIN_BUTTON = LocatorSpec(
    css=("#integrated-login a.btn-login", "a.btn-login"),
    role="link",
    role_names=("로그인하기",),
)

OTHER_LISTING = LocatorSpec(
    css=("button.btnOtherItem",),
    role="button",
    role_names=("다른 매물 등록",),
)
ONE_ROOM_LARGE = LocatorSpec(
    css=("label[for='saleTypeD']",),
    text=("원룸",),
)
ONE_ROOM_DETAIL = LocatorSpec(
    css=("#detailTypeitemOR", "button[data-offerings='OR']"),
    role="button",
    role_names=("원룸",),
)

ADDRESS_CONFIRM = LocatorSpec(
    css=("button.btn-address-confirm",),
    role="button",
    role_names=("주소확인(필수)", "주소확인"),
)
SUBMIT_BUTTON = LocatorSpec(
    css=("#offeringsAdSave", "button.btnConfirm"),
    role="button",
    role_names=("광고하기", "등록하기"),
)

POPUP_DISMISS_TEXTS = (
    "오늘 하루 보지 않기",
    "오늘 하루 보지않기",
    "오늘은 그만 보기",
)
POPUP_CLOSE_TEXTS = ("닫기", "창 닫기")

DIRECTION_LABELS = {
    "동": "동",
    "동향": "동",
    "서": "서",
    "서향": "서",
    "남": "남",
    "남향": "남",
    "북": "북",
    "북향": "북",
    "남동": "남동",
    "남동향": "남동",
    "남서": "남서",
    "남서향": "남서",
    "북동": "북동",
    "북동향": "북동",
    "북서": "북서",
    "북서향": "북서",
}

DIRECTION_CODES = {
    "동": "E",
    "서": "W",
    "남": "S",
    "북": "N",
    "남동": "SE",
    "남서": "SW",
    "북동": "NE",
    "북서": "NW",
}

DIRECTION_BASIS = {
    "거실": ("label[for='livingroom']", "#livingroom", "A"),
    "livingroom": ("label[for='livingroom']", "#livingroom", "A"),
    "안방": ("label[for='mainroom']", "#mainroom", "B"),
    "mainroom": ("label[for='mainroom']", "#mainroom", "B"),
}

DEAL_CODES = {
    "sale": "S",
    "매매": "S",
    "jeonse": "L",
    "전세": "L",
    "monthly": "M",
    "월세": "M",
    "short": "T",
    "단기임대": "T",
}

DEAL_LABELS = {
    "S": "매매",
    "L": "전세",
    "M": "월세",
    "T": "단기임대",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}

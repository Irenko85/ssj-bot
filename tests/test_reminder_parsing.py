from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from utils import reminders_store

TZ = "America/Santiago"


def _fixed_now() -> datetime:
    return datetime(2026, 5, 3, 10, 30, tzinfo=ZoneInfo(TZ))


def _patch_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reminders_store, "_now_in_timezone", lambda tz: _fixed_now())


def test_parse_when_accepts_hoy(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    result = reminders_store.parse_when("hoy", "21:00", TZ)

    expected = datetime(2026, 5, 3, 21, 0, tzinfo=ZoneInfo(TZ)).astimezone(
        timezone.utc
    )
    assert result == expected


def test_parse_when_accepts_manana(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    result = reminders_store.parse_when("mañana", "08:15", TZ)

    expected = datetime(2026, 5, 4, 8, 15, tzinfo=ZoneInfo(TZ)).astimezone(
        timezone.utc
    )
    assert result == expected


def test_parse_when_accepts_dd_mm(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    result = reminders_store.parse_when("25/05", "21:00", TZ)

    expected = datetime(2026, 5, 25, 21, 0, tzinfo=ZoneInfo(TZ)).astimezone(
        timezone.utc
    )
    assert result == expected


def test_parse_when_rejects_invalid_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    with pytest.raises(
        ValueError, match=r"Hora inválida\. Formato: hh:mm \(ej: 21:00\)"
    ):
        reminders_store.parse_when("hoy", "25:99", TZ)


def test_parse_when_rejects_invalid_date(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    with pytest.raises(
        ValueError, match=r"Fecha inválida\. Usa: hoy, mañana, o dd/mm"
    ):
        reminders_store.parse_when("32/05", "21:00", TZ)


def test_parse_when_rejects_single_digit_date(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    with pytest.raises(
        ValueError, match=r"Fecha inválida\. Usa: hoy, mañana, o dd/mm"
    ):
        reminders_store.parse_when("1/2", "21:00", TZ)


def test_parse_when_rejects_single_digit_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    with pytest.raises(
        ValueError, match=r"Hora inválida\. Formato: hh:mm \(ej: 21:00\)"
    ):
        reminders_store.parse_when("hoy", "9:5", TZ)


def test_parse_when_dd_mm_rolls_over_to_next_year(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    result = reminders_store.parse_when("01/02", "21:00", TZ)

    expected = datetime(2027, 2, 1, 21, 0, tzinfo=ZoneInfo(TZ)).astimezone(
        timezone.utc
    )
    assert result == expected


def test_parse_when_rejects_past_date(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_now(monkeypatch)

    with pytest.raises(ValueError, match=r"Esa fecha ya pasó 😅"):
        reminders_store.parse_when("hoy", "09:00", TZ)

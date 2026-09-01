from __future__ import annotations

from datetime import datetime, time

import pytest

from rtwi.models import Config, Schedule, is_within_schedule

# --- Schedule model ---


def test_schedule_defaults() -> None:
    s = Schedule()
    assert s.enabled is False
    assert s.start == time(8, 0)
    assert s.end == time(22, 0)
    assert s.days == [0, 1, 2, 3, 4]


def test_schedule_custom() -> None:
    s = Schedule(
        enabled=True, start=time(8, 30), end=time(17, 30), days=[0, 1, 2, 3, 4]
    )
    assert s.enabled is True
    assert s.start == time(8, 30)


def test_schedule_days_deduped_and_sorted() -> None:
    s = Schedule(days=[4, 2, 0, 2, 4])
    assert s.days == [0, 2, 4]


def test_schedule_invalid_day() -> None:
    with pytest.raises(ValueError, match=r"day must be 0\.\.6"):
        Schedule(days=[7])


# --- is_within_schedule ---


def test_disabled_always_within() -> None:
    s = Schedule(enabled=False)
    assert is_within_schedule(s, datetime(2025, 1, 1, 3, 0)) is True


def test_weekday_within_window() -> None:
    # 2025-01-06 is Monday
    s = Schedule(enabled=True, start=time(9, 0), end=time(18, 0), days=[0, 1, 2, 3, 4])
    assert is_within_schedule(s, datetime(2025, 1, 6, 12, 0)) is True


def test_weekday_outside_window() -> None:
    # Monday at 20:00
    s = Schedule(enabled=True, start=time(9, 0), end=time(18, 0), days=[0, 1, 2, 3, 4])
    assert is_within_schedule(s, datetime(2025, 1, 6, 20, 0)) is False


def test_weekday_before_start() -> None:
    s = Schedule(enabled=True, start=time(9, 0), end=time(18, 0), days=[0, 1, 2, 3, 4])
    assert is_within_schedule(s, datetime(2025, 1, 6, 8, 59)) is False


def test_weekday_at_boundary() -> None:
    s = Schedule(enabled=True, start=time(9, 0), end=time(18, 0), days=[0, 1, 2, 3, 4])
    assert is_within_schedule(s, datetime(2025, 1, 6, 9, 0)) is True
    assert is_within_schedule(s, datetime(2025, 1, 6, 18, 0)) is True


def test_weekend_not_in_days() -> None:
    # 2025-01-04 is Saturday (weekday=5)
    s = Schedule(enabled=True, start=time(0, 0), end=time(23, 59), days=[0, 1, 2, 3, 4])
    assert is_within_schedule(s, datetime(2025, 1, 4, 12, 0)) is False


def test_wrap_past_midnight_within() -> None:
    # schedule 22:00-06:00, check at 23:00 on Monday
    s = Schedule(enabled=True, start=time(22, 0), end=time(6, 0), days=[0, 1, 2, 3, 4])
    assert is_within_schedule(s, datetime(2025, 1, 6, 23, 0)) is True


def test_wrap_past_midnight_other_side() -> None:
    # schedule 22:00-06:00, check at 03:00 on Monday
    s = Schedule(enabled=True, start=time(22, 0), end=time(6, 0), days=[0, 1, 2, 3, 4])
    assert is_within_schedule(s, datetime(2025, 1, 7, 3, 0)) is True


def test_wrap_past_midnight_outside() -> None:
    # schedule 22:00-06:00, check at 12:00 on Monday
    s = Schedule(enabled=True, start=time(22, 0), end=time(6, 0), days=[0, 1, 2, 3, 4])
    assert is_within_schedule(s, datetime(2025, 1, 6, 12, 0)) is False


# --- Config with schedule ---


def test_config_schedule_default() -> None:
    cfg = Config()
    assert cfg.schedule.enabled is False
    assert cfg.schedule.start == time(8, 0)


def test_config_schedule_roundtrip() -> None:
    cfg = Config(schedule=Schedule(enabled=True, start=time(8, 0), end=time(20, 0)))
    data = cfg.model_dump(mode="json")
    restored = Config(**data)
    assert restored.schedule.enabled is True
    assert restored.schedule.start == time(8, 0)

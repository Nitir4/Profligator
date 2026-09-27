from datetime import date

from profligator_api.repository import _streaks


def test_streaks_distinguish_current_and_longest_runs() -> None:
    today = date(2026, 9, 25)
    active_dates = {
        date(2026, 9, 10),
        date(2026, 9, 11),
        date(2026, 9, 12),
        date(2026, 9, 24),
        date(2026, 9, 25),
    }

    current, longest = _streaks(active_dates, today)

    assert current == 2
    assert longest == 3


def test_current_streak_allows_activity_ending_yesterday() -> None:
    current, longest = _streaks(
        {date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24)},
        date(2026, 9, 25),
    )

    assert current == 3
    assert longest == 3

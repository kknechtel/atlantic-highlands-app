"""Future-dated recordings: a mistyped year in the town's filename."""
from datetime import date

from services.meeting_dates import correct_future_date, year_from_url

TODAY = date(2026, 10, 29)


def test_mistyped_year_takes_the_url_year_or_current_year():
    url = "https://www.ahnj.com/ahnj/Administration/Council%20Recordings/2029.09.09%20Council%20Recording.wma"
    assert year_from_url(url) is None
    assert correct_future_date("2029-09-09", today=TODAY) == "2026-09-09"
    assert correct_future_date("2027-03-05", url_year=2026, today=TODAY) == "2026-03-05"


def test_date_still_ahead_this_year_falls_back_a_year():
    assert correct_future_date("2029-12-15", today=TODAY) == "2025-12-15"


def test_past_and_today_are_left_alone():
    assert correct_future_date("2026-10-19", today=TODAY) is None
    assert correct_future_date("2026-10-29", today=TODAY) is None
    assert correct_future_date("not a date", today=TODAY) is None


def test_year_from_harbor_folder():
    assert year_from_url("https://x/AH%20Harbor/2025%20Recordings/Harbor%2004.07.wma") == 2025

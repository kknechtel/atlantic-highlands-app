"""Dates the library sorts by, from filenames and the top of the text."""
from services.title_extractor import _extract_date_from_filename, derive_from_text


def test_filename_date_formats():
    cases = {
        "Departments - Planning Board - Agendas and Minutes - PB Agenda 08.04.2022.pdf": "2022-08-04",
        "6.12.2024HHRSRegularBOEMeetingMinutes.pdf": "2024-06-12",
        "Agendas - Archives - 2005 - 11-09 REGULAR MEETINGMinutes.pdf": "2005-11-09",
        "Shade Tree Commission - Minutes - 2025 Minutes - August 2025.pdf": "2025-08",
        "October 28, 2026 HHRSD Regular BOE Meeting Agenda.pdf": "2026-10-28",
        "2024_03_06 Council.pdf": "2024-03-06",
    }
    for name, want in cases.items():
        assert _extract_date_from_filename(name) == want, name


def test_filename_without_date():
    assert _extract_date_from_filename("2024 Adopted Budget.pdf") is None
    assert _extract_date_from_filename("ORD 01-2026 Salary Ordinance.pdf") is None


def test_text_date_inside_a_line_and_with_direction_marks():
    assert derive_from_text("## Page 1 MINUTES OF THE MAYOR & COUNCIL REGULAR MEETING OF NOVEMBER 9, 2005 The")["doc_date"] == "2005-11-09"
    assert derive_from_text("‭HENRY HUDSON REGIONAL BOARD OF EDUCATION‬\n‭JUNE 12, 2024‬\nminutes")["doc_date"] == "2024-06-12"

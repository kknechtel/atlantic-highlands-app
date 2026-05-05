"""
OPRA Request PDF generator.

Produces a 1-3 page PDF that mirrors the layout of the NJ DCA model OPRA
request form (the same form Atlantic Highlands and Henry Hudson Regional
School District publish):

  Page 1 — Form face. Header with the agency name/address/phone, "Important
           Notice" strip, requestor info on the left, payment info on the
           right, certifications block, records-description box, and the
           three "AGENCY USE ONLY" panels along the bottom.
  Page 2 — Detailed records request (only when the description is too long
           to fit cleanly inside the page-1 box, or the requestor supplies
           additional context). The page-1 box gets a one-line pointer
           ("See attached: Detailed Records Request") and the attachment
           carries the full structured detail. This is the "don't cram"
           pattern: a custodian can act on a clear, well-organized 1-page
           description faster than on a wall of text squeezed into a
           form field.
  Page 3 — "Important Notice — Your Rights Under OPRA". The 13 numbered
           statements that NJ requires custodians to attach to OPRA
           response forms. Reproduced verbatim from the NJ DCA model form.

Two entities are supported via `entity`:
  - "borough"  → Borough of Atlantic Highlands (Michelle Clark, Clerk)
  - "school"   → Henry Hudson Regional School District (Janet Sherlock,
                  School Business Administrator)

Add a new entity by extending AGENCY_INFO.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak,
    KeepTogether,
)


# ── Agency definitions ───────────────────────────────────────────────────────

AGENCY_INFO = {
    "borough": {
        "agency_name": "Borough of Atlantic Highlands",
        "form_title": "OPEN PUBLIC RECORDS ACT REQUEST FORM",
        "address_line": "100 First Ave, Atlantic Highlands, NJ 07716",
        "phone": "(732) 291-1444",
        "email": "clerk@ahnj.com",
        "custodian_name": "Michelle Clark",
        "custodian_title": "Municipal Clerk",
        "submission_note": (
            "Submit by email to clerk@ahnj.com, by mail/in person at 100 First "
            "Ave, Atlantic Highlands, NJ 07716, or via the Borough's GovPilot "
            "OPRA portal."
        ),
    },
    "school": {
        "agency_name": "Henry Hudson Regional School District",
        "form_title": "OPEN PUBLIC RECORDS ACT REQUEST FORM",
        "address_line": "1 Grand Tour, Highlands, NJ 07732",
        "phone": "(732) 872-0900 ext. 4001",
        "email": "jsherlock@henryhudsonreg.k12.nj.us",
        "custodian_name": "Janet Sherlock",
        "custodian_title": "School Business Administrator / Board Secretary",
        "submission_note": (
            "Email the completed form to Janet Sherlock, School Business "
            "Administrator, at jsherlock@henryhudsonreg.k12.nj.us. Mail or "
            "fax (732-872-1315) also accepted. The district consolidated on "
            "July 1, 2024 — predecessor districts (Atlantic Highlands SD, "
            "Highlands SD, HHR HS) no longer maintain separate custodians."
        ),
    },
}


# ── Styles ───────────────────────────────────────────────────────────────────

_styles = getSampleStyleSheet()
TITLE = ParagraphStyle(
    "OPRATitle", parent=_styles["Heading1"],
    fontName="Helvetica-Bold", fontSize=12, leading=14, alignment=1,
    spaceBefore=0, spaceAfter=2,
)
AGENCY = ParagraphStyle(
    "OPRAAgency", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=10, leading=12, alignment=1,
)
H_NOTICE = ParagraphStyle(
    "OPRANoticeHeader", parent=_styles["Normal"],
    fontName="Helvetica-Bold", fontSize=9, leading=10, alignment=1,
)
LABEL = ParagraphStyle(
    "OPRALabel", parent=_styles["Normal"],
    fontName="Helvetica-Bold", fontSize=8, leading=10,
)
FIELD = ParagraphStyle(
    "OPRAField", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=8.5, leading=11,
)
SMALL = ParagraphStyle(
    "OPRASmall", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=7.5, leading=9,
)
CERT = ParagraphStyle(
    "OPRACert", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=8, leading=10,
)
H2 = ParagraphStyle(
    "OPRAH2", parent=_styles["Heading2"],
    fontName="Helvetica-Bold", fontSize=11, leading=13, spaceBefore=8, spaceAfter=4,
)
BODY = ParagraphStyle(
    "OPRABody", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=9.5, leading=12, spaceAfter=4,
)
NOTICE_ITEM = ParagraphStyle(
    "OPRANoticeItem", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=8.5, leading=10.5, leftIndent=18, firstLineIndent=-18,
    spaceAfter=4,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check(checked: bool) -> str:
    """Return a checkbox marker. ASCII brackets render reliably in
    Helvetica (Type-1) without an embedded TTF — the Unicode ballot-box
    glyphs (☐/☒) fall back to the missing-glyph square in Helvetica, so
    both checked and unchecked render identically. Use ASCII instead."""
    return "[X]" if checked else "[ ]"


def _filled(value: str, placeholder: str = "") -> str:
    """Render a form field value with a trailing underline so blank fields
    still look like the printed form's underline-rule fields. Uses HTML-ish
    paragraph markup that ParagraphStyle understands."""
    v = (value or "").strip()
    if v:
        # Bold-ish look: keep regular weight but underline so it reads like
        # a printed-form fill-in.
        return f'<u>{_escape(v)}</u>'
    if placeholder:
        return f'<font color="#888">{_escape(placeholder)}</font>'
    # 30 underscores reads as a blank form line.
    return "<font color='#999'>" + "_" * 30 + "</font>"


def _escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _request_should_attach(specific_records: str, additional_context: str) -> bool:
    """When to overflow into the attachment page.

    A custodian works through a stack of forms; cramming a multi-bullet,
    paragraph-length request into a 6-line form box is harder to act on
    than a one-line pointer + a clean attachment page. Trigger if:
      - the description is multi-paragraph, or
      - it's longer than what comfortably fits the form box (~600 chars), or
      - additional_context is non-empty (always belongs on the attachment
        rather than buried under the form box).
    """
    s = (specific_records or "").strip()
    if (additional_context or "").strip():
        return True
    if len(s) > 600:
        return True
    if s.count("\n\n") >= 1:  # multi-paragraph
        return True
    return False


# ── Page 1: form face ────────────────────────────────────────────────────────

def _build_header(info: dict):
    """Title + agency + address + phone + custodian — top of page 1."""
    rows = [
        [Paragraph(info["agency_name"], AGENCY)],
        [Paragraph(info["form_title"], TITLE)],
        [Paragraph(info["address_line"], AGENCY)],
        [Paragraph(info["phone"], AGENCY)],
        [Paragraph(f'<a href="mailto:{info["email"]}"><font color="#385854">{info["email"]}</font></a>', AGENCY)],
        [Paragraph(f'{info["custodian_name"]}, {info["custodian_title"]}', AGENCY)],
    ]
    t = Table(rows, colWidths=[7.5 * inch])
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _build_important_notice_strip():
    """The 1-line "Important Notice — see last page for rights" strip."""
    txt = (
        "<b>Important Notice</b>&nbsp;&nbsp;The last page of this form contains "
        "important information related to your rights concerning government records. "
        "Please read it carefully."
    )
    p = Paragraph(txt, H_NOTICE)
    t = Table([[p]], colWidths=[7.5 * inch])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _build_requestor_and_payment(req: dict, info: dict):
    """Side-by-side requestor info (left ~70%) + payment info (right ~30%)."""

    name_full = " ".join(p for p in [
        req.get("requestor_name", ""),
    ] if p).strip()

    pref = (req.get("preferred_format") or "electronic").lower()
    pref_pickup = "X" if pref == "pickup" else ""
    pref_mail = "X" if pref == "mail" else ""
    pref_inspect = "X" if pref == "inspect" else ""
    pref_fax = "X" if pref == "fax" else ""
    pref_email = "X" if pref in ("electronic", "email") else ""

    cert_have = bool(req.get("cert_no_indictable", True))      # "HAVE NOT been convicted"
    cert_will = bool(req.get("cert_not_commercial", True))     # "WILL NOT use for commercial"
    cert_litigation = bool(req.get("cert_litigation", False))  # "AM seeking ... legal proceeding"

    cert_block = (
        '<font size="7.5">Under penalty of <u>N.J.S.A.</u> 2C:28-3, I certify that:</font><br/>'
        f'<font size="7.5">1. I {_check(False)} HAVE / {_check(cert_have)} HAVE NOT '
        'been convicted of any indictable offense under the laws of New Jersey, '
        'any other state, or the United States;</font><br/>'
        f'<font size="7.5">2. I, or another person, {_check(False)} WILL / '
        f'{_check(cert_will)} WILL NOT use the requested government records for a '
        'commercial purpose;</font><br/>'
        f'<font size="7.5">3. I {_check(cert_litigation)} AM / '
        f'{_check(not cert_litigation)} AM NOT seeking records in connection with '
        'a legal proceeding.</font>'
    )

    requestor_inner = [
        [Paragraph("<b>Requestor Information</b> &mdash; Please Print", LABEL)],
        [Paragraph(f"Name: {_filled(name_full, '[Full Name]')}", FIELD)],
        [Paragraph(f"E-mail Address: {_filled(req.get('requestor_email', ''))}", FIELD)],
        [Paragraph(f"Mailing Address: {_filled(req.get('requestor_address', ''))}", FIELD)],
        [Paragraph(f"Telephone: {_filled(req.get('requestor_phone', ''))}", FIELD)],
        [Paragraph(
            f"Preferred Delivery: "
            f"Pick&nbsp;Up&nbsp;[{pref_pickup}] "
            f"US&nbsp;Mail&nbsp;[{pref_mail}] "
            f"On-Site&nbsp;Inspect&nbsp;[{pref_inspect}] "
            f"Fax&nbsp;[{pref_fax}] "
            f"E-mail&nbsp;[{pref_email}]",
            FIELD,
        )],
        [Paragraph(cert_block, CERT)],
        [Paragraph(
            f"Signature: {'_' * 38}&nbsp;&nbsp;&nbsp;Date: {_filled(date.today().strftime('%B %d, %Y'))}",
            FIELD,
        )],
    ]
    requestor_table = Table(requestor_inner, colWidths=[5.0 * inch])
    requestor_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    payment_inner = [
        [Paragraph("<b>Payment Information</b>", LABEL)],
        [Paragraph(f"Maximum Authorization Cost: $ {_filled('')}", SMALL)],
        [Paragraph("<b>Select Payment Method:</b>", SMALL)],
        [Paragraph(f"{_check(False)} Cash &nbsp; {_check(False)} Check &nbsp; {_check(False)} Money&nbsp;Order", SMALL)],
        [Paragraph(
            "<b>Fees:</b> Letter-size: $0.05/page &middot; "
            "Legal-size: $0.07/page &middot; "
            "Other media (CD, DVD, etc.): actual cost.",
            SMALL,
        )],
        [Paragraph(
            "<b>Delivery:</b> Postage / delivery fees additional depending on method.",
            SMALL,
        )],
        [Paragraph(
            "<b>Extras:</b> Special service charge dependent upon request.",
            SMALL,
        )],
    ]
    payment_table = Table(payment_inner, colWidths=[2.4 * inch])
    payment_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    outer = Table(
        [[requestor_table, payment_table]],
        colWidths=[5.0 * inch, 2.5 * inch],
    )
    outer.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
        ("LINEAFTER", (0, 0), (0, 0), 0.75, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return outer


def _build_records_box(req: dict, attached: bool):
    """Records description box. If `attached` is True, write a one-line
    pointer to the attachment page rather than cramming the full text in."""
    intro = Paragraph(
        "<b>Record Request Information:</b> Please be as specific as possible in describing "
        "the records being requested. Your preferred method of delivery will only be "
        "accommodated if the custodian has the technological means and the integrity of the "
        "records will not be jeopardized by such method of delivery.",
        SMALL,
    )

    note_litigation = Paragraph(
        "<b>Note:</b> <i>If you confirmed above that the records sought are in connection "
        "with a legal proceeding, identification of that proceeding is required below.</i>",
        SMALL,
    )

    if attached:
        body_text = (
            "<b>See attached: Detailed Records Request</b><br/><br/>"
            "The records described in this request are itemized on the attached page "
            "(<i>Detailed Records Request &mdash; Attachment to Page 1</i>) so that the "
            "custodian can act on each item without ambiguity. The attachment is part of "
            "this request and is incorporated by reference."
        )
    else:
        body_text = _escape(req.get("specific_records", "")).replace("\n", "<br/>")

    body = Paragraph(body_text, FIELD)

    inner = [[intro], [Spacer(1, 4)], [note_litigation], [Spacer(1, 6)], [body]]
    t = Table(inner, colWidths=[7.5 * inch], rowHeights=[None, None, None, None, 2.4 * inch])
    t.setStyle(TableStyle([
        ("BOX", (0, 4), (-1, 4), 0.75, colors.black),
        ("VALIGN", (0, 4), (-1, 4), "TOP"),
        ("LEFTPADDING", (0, 4), (-1, 4), 6),
        ("RIGHTPADDING", (0, 4), (-1, 4), 6),
        ("TOPPADDING", (0, 4), (-1, 4), 6),
        ("BOTTOMPADDING", (0, 4), (-1, 4), 6),
    ]))
    return t


def _build_agency_use_panels():
    """The three "AGENCY USE ONLY" panels along the bottom of page 1."""
    cost_lines = [
        "Est. Document Cost: " + "_" * 14,
        "Est. Delivery Cost: " + "_" * 14,
        "Est. Extras Cost: " + "_" * 16,
        "Total Est. Cost: " + "_" * 18,
        "Deposit Amount: " + "_" * 18,
        "Estimated Balance: " + "_" * 16,
        "Deposit Date: " + "_" * 20,
    ]
    cost_block = "<br/>".join(cost_lines)

    disp_lines = [
        "<b>Disposition Notes</b>",
        "<i>Custodian: If any part of request cannot be delivered in seven business days, detail reasons here.</i>",
        "",
        "&nbsp;&nbsp;In Progress &nbsp;-&nbsp; Open " + "_" * 10,
        "&nbsp;&nbsp;Denied &nbsp;-&nbsp; Closed " + "_" * 10,
        "&nbsp;&nbsp;Filled &nbsp;-&nbsp; Closed " + "_" * 10,
        "&nbsp;&nbsp;Partial &nbsp;-&nbsp; Closed " + "_" * 10,
    ]
    disp_block = "<br/>".join(disp_lines)

    track_lines = [
        "<b>Tracking Information</b>",
        "Tracking #: " + "_" * 18,
        "Rec'd Date: " + "_" * 18,
        "Ready Date: " + "_" * 18,
        "",
        "<b>Final Cost</b>",
        "Total: " + "_" * 22,
        "Deposit: " + "_" * 20,
        "Balance Due: " + "_" * 16,
        "Total Pages: " + "_" * 16,
        "Balance Paid: " + "_" * 16,
        "<b>Records Provided</b>",
        "_" * 36,
        "Custodian Signature &nbsp;&nbsp; Date",
    ]
    track_block = "<br/>".join(track_lines)

    header_row = [
        Paragraph("<b>AGENCY USE ONLY</b>", H_NOTICE),
        Paragraph("<b>AGENCY USE ONLY</b>", H_NOTICE),
        Paragraph("<b>AGENCY USE ONLY</b>", H_NOTICE),
    ]
    body_row = [
        Paragraph(cost_block, SMALL),
        Paragraph(disp_block, SMALL),
        Paragraph(track_block, SMALL),
    ]
    t = Table([header_row, body_row], colWidths=[2.5 * inch, 2.5 * inch, 2.5 * inch])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
        ("LINEAFTER", (0, 0), (1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# ── Page 2: detailed attachment ──────────────────────────────────────────────

def _build_detailed_attachment(req: dict, info: dict, category_label: str):
    """Full structured detail. Paginates naturally if it overflows."""
    flow = []
    flow.append(Paragraph("Detailed Records Request &mdash; Attachment to Page 1", H2))
    flow.append(Paragraph(
        f"This attachment is part of the OPRA request submitted to "
        f"<b>{_escape(info['agency_name'])}</b> "
        f"({_escape(info['custodian_name'])}, {_escape(info['custodian_title'])}) "
        f"on {date.today().strftime('%B %d, %Y')} by "
        f"<b>{_escape(req.get('requestor_name') or '[Requestor]')}</b>.",
        BODY,
    ))
    flow.append(Spacer(1, 6))
    flow.append(Paragraph(f"<b>Record Category:</b> {_escape(category_label)}", BODY))
    if req.get("date_range_start") or req.get("date_range_end"):
        rng = (
            f"{req.get('date_range_start') or '...'} to "
            f"{req.get('date_range_end') or 'present'}"
        )
        flow.append(Paragraph(f"<b>Date Range:</b> {_escape(rng)}", BODY))
    fmt_label = {
        "electronic": "Electronic copies via email",
        "email": "Electronic copies via email",
        "copies": "Paper copies (statutory fee schedule applies)",
        "inspect": "On-site inspection at agency offices",
        "pickup": "Pick up in person",
        "mail": "U.S. Mail",
        "fax": "Fax",
    }.get((req.get("preferred_format") or "electronic").lower(), "Electronic copies")
    flow.append(Paragraph(f"<b>Preferred Delivery:</b> {_escape(fmt_label)}", BODY))
    flow.append(Spacer(1, 6))

    flow.append(Paragraph("Records Requested", H2))
    spec = req.get("specific_records", "").strip()
    if spec:
        for para in spec.split("\n\n"):
            text = para.replace("\n", "<br/>")
            flow.append(Paragraph(_escape_keep_breaks(text), BODY))
            flow.append(Spacer(1, 2))
    else:
        flow.append(Paragraph("<i>(no description provided)</i>", BODY))

    additional = (req.get("additional_context") or "").strip()
    if additional:
        flow.append(Paragraph("Additional Context", H2))
        for para in additional.split("\n\n"):
            text = para.replace("\n", "<br/>")
            flow.append(Paragraph(_escape_keep_breaks(text), BODY))
            flow.append(Spacer(1, 2))

    flow.append(Paragraph("Statutory Basis", H2))
    flow.append(Paragraph(
        "This request is made pursuant to the New Jersey Open Public Records Act, "
        "<u>N.J.S.A.</u> 47:1A-1 <i>et seq.</i>, as amended by P.L. 2024, c.16 "
        "(effective September 3, 2024). Per <u>N.J.S.A.</u> 47:1A-5, the custodian "
        "shall grant or deny access to the requested records as soon as possible, "
        "but no later than seven (7) business days after receipt (fourteen (14) "
        "business days for commercial-purpose requests). Records identified as "
        "&ldquo;immediately accessible&rdquo; under <u>N.J.S.A.</u> 47:1A-5(e) "
        "(budgets, bills, vouchers, contracts, meeting minutes, resolutions, "
        "ordinances, salary information) must be provided without delay.",
        BODY,
    ))
    flow.append(Paragraph(
        "If any portion of the requested records is exempt under "
        "<u>N.J.S.A.</u> 47:1A-1.1, 47:1A-3, 47:1A-9, 47:1A-10, or any other applicable "
        "provision, the custodian is requested to redact the exempt portions and "
        "provide the remainder, citing the specific exemption(s) for any redactions or "
        "denials. Partial denials must be supported by the specific statutory basis "
        "per <u>N.J.S.A.</u> 47:1A-5(g).",
        BODY,
    ))

    return flow


def _escape_keep_breaks(s: str) -> str:
    out = (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return out.replace("[br/]", "<br/>")


# ── Page 3: rights notice (verbatim from NJ DCA model form) ──────────────────

_RIGHTS_NOTICES = [
    'All "government records" as defined in <u>N.J.S.A.</u> 47:1A-1.1 are subject to '
    'public access under the Open Public Records Act ("OPRA"), unless specifically exempt.',

    'A request for access to a government record under OPRA must be in writing, '
    'hand-delivered, mailed, transmitted electronically, or otherwise conveyed to the '
    'appropriate custodian. <u>N.J.S.A.</u> 47:1A-5(g). In accordance with OPRA, '
    'custodians will generally have seven (7) business days to respond, with longer '
    'time frames for commercial-purpose requests (14 business days), Daniel’s Law '
    'compliance reviews (14 business days), and certain other categories. The applicable '
    'response time does not commence until the custodian receives the request form. '
    '<u>N.J.S.A.</u> 47:1A-5(h).',

    'Requestors are not required to use this OPRA request form; however, a written '
    'equivalent not containing the form requirements of <u>N.J.S.A.</u> 47:1A-5(f) and '
    '<u>N.J.S.A.</u> 47:1A-5(g) may be denied by a custodian.',

    'Requestors may submit requests anonymously. A request submitted anonymously shall '
    'not be considered incomplete. <u>N.J.S.A.</u> 47:1A-5(f). However, anonymous '
    'requestors are prohibited from filing a complaint with either the Government '
    'Records Council or the Courts. <u>N.J.S.A.</u> 47:1A-6.',

    'The fees for duplication of a "government record" in printed form are listed on '
    'page 1 of this form. The custodian will notify you of any special service charges '
    'or other additional charges authorized by State law or regulation before processing '
    'your request. Payment shall be made by cash, check or money order payable to the '
    'responding agency.',

    'You may be charged a prepayment or deposit when a request for copies exceeds $5.00. '
    'The custodian will contact you and advise you of any deposit requirements. You '
    'agree to pay the balance due upon delivery of the records.',

    'Under OPRA, a custodian must deny access to a person who has been convicted of an '
    'indictable offense in New Jersey, any other state, or the United States, and who is '
    'seeking government records containing personal information pertaining to the '
    'person’s victim or the victim’s family. <u>N.J.S.A.</u> 47:1A-2.2.',

    'By law, the responding agency must notify you that it grants or denies a request '
    'within the applicable response time frame. If the record requested is in storage, '
    'the custodian will advise you within seven (7) or fourteen (14) business days after '
    'receipt when the record can be made available, and shall provide it within no more '
    'than twenty-one (21) business days from date of notification. <u>N.J.S.A.</u> '
    '47:1A-5(i).',

    'You may be denied access to a government record if your request would substantially '
    'disrupt agency operations and the custodian is unable to reach a reasonable '
    'solution with you. <u>N.J.S.A.</u> 47:1A-5(g).',

    'If the custodian is unable to comply with your request, they will indicate the '
    'specific bases for denial on the request form or other written correspondence and '
    'send it to you.',

    'Except as otherwise provided by law or by agreement, if the custodian fails to '
    'respond to you in writing within seven (7) or fourteen (14) business days of '
    'receiving a request, the failure to respond is a deemed denial. <u>N.J.S.A.</u> '
    '47:1A-5(g); <u>N.J.S.A.</u> 47:1A-5(i).',

    'If your request has been denied or unfilled within the seven (7) or fourteen (14) '
    'business days required by law, you may either (1) institute a proceeding in the '
    'Superior Court of New Jersey, or (2) file a complaint with the Government Records '
    'Council ("GRC") by completing the Denial of Access Complaint Form. GRC: '
    '866-850-0511, PO Box 819, Trenton, NJ 08625, '
    'Government.Records@dca.nj.gov, www.state.nj.us/grc.',

    'Information provided on this form may be subject to disclosure under the Open '
    'Public Records Act.',
]


def _build_rights_notice():
    flow = [Paragraph("Important Notice &mdash; Your Rights Under OPRA", H2)]
    flow.append(Paragraph(
        "The following statements are reproduced from the NJ Department of Community "
        "Affairs model OPRA request form pursuant to <u>N.J.S.A.</u> 47:1A et seq. and "
        "P.L. 2024, c.16. They describe your rights and the custodian’s obligations "
        "and are part of this request.",
        BODY,
    ))
    flow.append(Spacer(1, 6))
    for i, txt in enumerate(_RIGHTS_NOTICES, 1):
        flow.append(Paragraph(f"{i}.&nbsp;&nbsp;{txt}", NOTICE_ITEM))
    return flow


# ── Public entry point ───────────────────────────────────────────────────────

def render_opra_pdf(
    req: dict,
    entity: str = "borough",
    category_label: Optional[str] = None,
) -> bytes:
    """Render an OPRA request as a PDF. Returns the PDF bytes.

    Required `req` keys (all strings, missing → empty):
      requestor_name, requestor_email, requestor_address, requestor_phone,
      specific_records, additional_context, preferred_format,
      date_range_start, date_range_end.
    Optional `req` keys (booleans):
      cert_no_indictable    (default True  → "HAVE NOT been convicted")
      cert_not_commercial   (default True  → "WILL NOT use for commercial")
      cert_litigation       (default False → "AM NOT in legal proceeding")
    """
    info = AGENCY_INFO.get(entity) or AGENCY_INFO["borough"]
    attached = _request_should_attach(
        req.get("specific_records", ""),
        req.get("additional_context", ""),
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.4 * inch, bottomMargin=0.4 * inch,
        title=f"OPRA Request — {info['agency_name']}",
        author=req.get("requestor_name", "OPRA Requestor"),
    )

    story = []
    story.append(_build_header(info))
    story.append(Spacer(1, 4))
    story.append(_build_important_notice_strip())
    story.append(Spacer(1, 4))
    story.append(_build_requestor_and_payment(req, info))
    story.append(Spacer(1, 6))
    story.append(_build_records_box(req, attached))
    story.append(Spacer(1, 6))
    story.append(_build_agency_use_panels())
    story.append(PageBreak())

    if attached:
        story.extend(_build_detailed_attachment(
            req, info, category_label or "(unspecified)",
        ))
        story.append(PageBreak())

    story.extend(_build_rights_notice())

    doc.build(story)
    return buf.getvalue()

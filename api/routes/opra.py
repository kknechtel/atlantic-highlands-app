"""
OPRA Request Generator - Generate legally compliant Open Public Records Act requests
for the Borough of Atlantic Highlands, NJ.

Legal basis: N.J.S.A. 47:1A-1 et seq., as amended by P.L. 2024, c.16 (eff. 9/3/2024).
"""
import logging
import json
import asyncio
from datetime import datetime, date
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)
router = APIRouter()

# ── OPRA Regulatory Reference ────────────────────────────────────────────────
# This is compiled from N.J.S.A. 47:1A-1 et seq. and P.L. 2024, c.16.
# It is loaded before every generation and fact-check call.

OPRA_REGULATIONS = """
=== NEW JERSEY OPEN PUBLIC RECORDS ACT (OPRA) ===
=== N.J.S.A. 47:1A-1 et seq., as amended by P.L. 2024, c.16 (eff. Sept 3, 2024) ===

SECTION 1 - DECLARATION OF POLICY (N.J.S.A. 47:1A-1)
Government records shall be readily accessible for inspection, copying, or examination
by the citizens of this State, with certain exceptions, for the protection of the public
interest. All limitations on the right of access shall be construed in favor of the
public's right of access.

SECTION 2 - DEFINITIONS (N.J.S.A. 47:1A-1.1)
- "Government record" or "record": Any paper, written or printed book, document,
  drawing, map, plan, photograph, microfilm, data processed or image processed document,
  information stored or maintained electronically or by sound-recording or in a similar
  device, or any copy thereof, that has been made, maintained or kept on file in the
  course of official business by any officer, commission, agency or authority of the
  State or of any political subdivision thereof.
  EXCLUDES: inter-agency or intra-agency advisory, consultative, or deliberative (ACD)
  material.
- "Custodian of a government record" or "custodian": For municipalities, the municipal
  clerk (or formally designated records custodian).
- "Public agency": Any of the principal departments in the Executive Branch of State
  Government, the Legislature, any independent State authority, commission, instrumentality
  or agency, and any political subdivision of the State or any agency or instrumentality
  thereof.
- "Commercial purpose": The direct or indirect use of any part of a government record(s)
  for sale, resale, solicitation, rent, or lease of a service, or any use by which the
  requestor will derive a fee, commission, salary, or financial benefit. (P.L. 2024, c.16)
  EXEMPT from commercial classification: journalists, news organizations, educational/
  scientific/scholarly institutions, government entities, political candidates/committees,
  labor unions, nonprofits not selling the records.

SECTION 3 - ACCESS (N.J.S.A. 47:1A-5)
(a) The custodian shall grant or deny access to the requested record as soon as possible,
    but no later than seven (7) business days after receiving the request.
    For commercial-purpose requests: fourteen (14) business days. (P.L. 2024, c.16)
(b) If the custodian is unable to comply within the time frame, the custodian shall
    indicate the specific basis therefor on the request form and promptly provide the
    requestor with a date certain for when the record will be made available.
(c) If a requested record is in storage or archived, the custodian shall so advise the
    requestor within the 7/14 business day period and shall provide the record within
    21 business days from notification.
(d) A custodian shall not require a requestor to state a reason for requesting records.

SECTION 4 - REQUEST FORM REQUIREMENTS (N.J.S.A. 47:1A-5, P.L. 2024, c.16)
All requests must be submitted:
- In writing (hand-delivered, mailed, emailed, or faxed during regular business hours)
- On the agency's official OPRA request form or the GRC model form
- Must include: requestor name, mailing address, email, and phone number
- Must include: certification regarding commercial purpose
- Must include: certification regarding pending litigation
- Must be signed and dated
- Anonymous requests are permitted but cannot be challenged in court if denied

SECTION 5 - FEES (N.J.S.A. 47:1A-5)
(a) Letter-size pages (8.5" x 11" or smaller): $0.05 per page
(b) Legal-size pages (8.5" x 14" or larger): $0.07 per page
(c) Electronic records: actual cost of the storage medium only
(d) Special service charge: authorized when fulfillment requires extraordinary
    expenditure of time and effort (must be reasonable, based on actual direct cost)
(e) Postage: actual cost of mailing

ATLANTIC HIGHLANDS SPECIFIC:
- Custodian: Municipal Clerk, Borough of Atlantic Highlands
  Contact: 732-291-1444 x3103
- Mailing address for envelopes: $0.25 per envelope plus postage
- Online submissions via GovPilot portal

SECTION 6 - IMMEDIATE ACCESS RECORDS (N.J.S.A. 47:1A-5)
The following records are deemed immediately accessible and must be provided without delay:
- Budgets
- Bills
- Vouchers
- Contracts
- Meeting minutes
- Resolutions and ordinances
- Salary and overtime information
- Professional service agreements
- Records less than 24 months old in common categories

SECTION 7 - EXEMPTIONS (N.J.S.A. 47:1A-1.1, 47:1A-3, 47:1A-9, 47:1A-10)
The following are exempt from disclosure:
1. Advisory, Consultative, or Deliberative (ACD) material (N.J.S.A. 47:1A-1.1)
2. Criminal investigatory records (N.J.S.A. 47:1A-1.1)
3. Victims' records (N.J.S.A. 47:1A-1.1)
4. Trade secrets / proprietary commercial information (N.J.S.A. 47:1A-1.1)
5. Attorney-client privileged materials (N.J.S.A. 47:1A-1.1)
6. Personnel records (general personnel files, with exceptions for name, title,
   position, salary, payroll, length of service, dates of hire/separation,
   which ARE public) (N.J.S.A. 47:1A-10)
7. Pension records (except name, type, value of benefit) (N.J.S.A. 47:1A-10)
8. Medical examiner photos/autopsy details (N.J.S.A. 47:1A-1.1)
9. Computer security information (N.J.S.A. 47:1A-1.1)
10. Building security information and surveillance footage (N.J.S.A. 47:1A-1.1)
11. Social Security numbers (N.J.S.A. 47:1A-1.1)
12. Credit card / bank account numbers (N.J.S.A. 47:1A-1.1)
13. Driver's license numbers (N.J.S.A. 47:1A-1.1)
14. Home addresses of judges, prosecutors, law enforcement (N.J.S.A. 47:1A-1.1)
15. Juvenile records with personal identifying information (N.J.S.A. 47:1A-1.1)
16. Personal firearms records (N.J.S.A. 47:1A-1.1)
17. Emergency/security plans and procedures (N.J.S.A. 47:1A-1.1)
18. Legislative constituent communications (N.J.S.A. 47:1A-1.1)
19. IT security protocols (N.J.S.A. 47:1A-1.1)
20. Records subject to privacy interest under Executive Order 26 (Whitman, 1995)
21. Records exempt under other statutes (e.g., HIPAA, tax records, etc.)

SECTION 8 - DENIAL PROCEDURE (N.J.S.A. 47:1A-5)
- Custodian must specify the legal basis for denial on the request form
- Partial denials require redaction of only the exempt portions; remaining content
  must be provided
- Requestor must be notified promptly of the denial and the specific exemption(s)

SECTION 9 - REMEDIES (N.J.S.A. 47:1A-6)
A requestor denied access may, within 45 days:
(a) File an action in Superior Court in the county where the record is held; OR
(b) File a complaint with the Government Records Council (GRC)
- A requestor who prevails is entitled to reasonable attorney's fees
- If the denial was unreasonable or in bad faith, attorney's fees are mandatory
- The GRC must adjudicate within 90 days (45-day extension for good cause)

SECTION 10 - PENALTIES (N.J.S.A. 47:1A-11)
Custodians who knowingly and willfully violate OPRA with unreasonable denial:
- 1st offense: $1,000 civil penalty
- 2nd offense (within 10 years): $2,500
- 3rd+ offense (within 10 years): $5,000
Requestors who intentionally fail to certify commercial purpose:
- $1,000 to $5,000 civil penalty

SECTION 11 - ELECTION RECORDS (P.L. 2024, c.16)
Voter registration forms, party affiliation records, vote-by-mail applications,
nominating petitions: 2-business-day response requirement.
Records within 16 days of an election: 2-business-day response for voter activity lists.

SECTION 12 - PROTECTIVE ORDERS (P.L. 2024, c.16)
Courts may limit access for requestors seeking records to "substantially interrupt
government function" (clear and convincing evidence standard).
"""

ATLANTIC_HIGHLANDS_INFO = """
=== ATLANTIC HIGHLANDS BOROUGH - OPRA SUBMISSION INFO ===
Municipality: Borough of Atlantic Highlands, Monmouth County, New Jersey
Records Custodian: Municipal Clerk
Phone: 732-291-1444 x3103
GovPilot Online Form: https://main.govpilot.com/web/public/2b3162a4-a0f_OPRA-ahadmin?uid=6865&ust=NJ&pu=1&id=1
Physical Address: 100 First Avenue, Atlantic Highlands, NJ 07716
Fee Schedule:
  - Letter-size copies: $0.05/page (N.J.S.A. 47:1A-5)
  - Legal-size copies: $0.07/page (N.J.S.A. 47:1A-5)
  - Envelopes: $0.25 each plus postage
  - Electronic delivery: no charge for the medium
"""

# ── Record Category Templates ────────────────────────────────────────────────

RECORD_CATEGORIES = {
    "financial": {
        "label": "Financial/Budget Records",
        "description": "Municipal budgets, audit reports, expenditure records, revenue reports",
        "example_records": [
            "Annual municipal budget for fiscal year [YEAR]",
            "Comprehensive Annual Financial Report (CAFR) for fiscal year [YEAR]",
            "Monthly treasurer's reports from [START DATE] to [END DATE]",
            "All purchase orders and vouchers exceeding $[AMOUNT] from [DATE RANGE]",
            "Bank statements for all municipal accounts from [DATE RANGE]",
            "Capital improvement plan and associated expenditure records",
        ],
        "notes": "Budget records are 'immediate access' records under N.J.S.A. 47:1A-5. Bills, vouchers, and contracts are also immediate access.",
    },
    "contracts": {
        "label": "Contracts & Agreements",
        "description": "Professional service agreements, vendor contracts, leases",
        "example_records": [
            "All professional service contracts awarded in calendar year [YEAR]",
            "Contract between the Borough and [VENDOR NAME] for [SERVICE]",
            "All vendor contracts exceeding $[AMOUNT] executed since [DATE]",
            "Request for proposals (RFPs) issued for [SERVICE TYPE] in [YEAR]",
            "Insurance policies and broker agreements currently in effect",
        ],
        "notes": "Contracts are 'immediate access' records under N.J.S.A. 47:1A-5.",
    },
    "meetings": {
        "label": "Meeting Minutes & Resolutions",
        "description": "Council minutes, resolutions, ordinances, agendas",
        "example_records": [
            "Borough Council meeting minutes from [DATE] to [DATE]",
            "All resolutions adopted by the Borough Council in [YEAR]",
            "Ordinances introduced and/or adopted in [YEAR]",
            "Planning Board meeting minutes from [DATE RANGE]",
            "Zoning Board of Adjustment meeting minutes from [DATE RANGE]",
        ],
        "notes": "Meeting minutes and resolutions are 'immediate access' records under N.J.S.A. 47:1A-5.",
    },
    "personnel": {
        "label": "Personnel & Salary Records",
        "description": "Employee names, titles, salaries, overtime (public portions only)",
        "example_records": [
            "Names, titles, and annual salaries of all current Borough employees",
            "Overtime records for all departments from [DATE RANGE]",
            "Dates of hire, separation, and length of service for [DEPARTMENT]",
            "Position descriptions and salary ranges for all municipal positions",
        ],
        "notes": "Per N.J.S.A. 47:1A-10, name, title, position, salary, payroll record, length of service, date of separation, and reason for separation ARE public. General personnel files are exempt.",
    },
    "permits": {
        "label": "Permits & Applications",
        "description": "Building permits, zoning applications, construction permits",
        "example_records": [
            "All building permits issued for [ADDRESS or BLOCK/LOT]",
            "Zoning applications and decisions for [ADDRESS or BLOCK/LOT] from [DATE RANGE]",
            "Certificate of occupancy for [ADDRESS]",
            "Construction permits and inspection reports for [ADDRESS]",
        ],
        "notes": "Permit records are generally public. Property-specific requests should include block and lot numbers when possible.",
    },
    "police": {
        "label": "Police/Public Safety Records",
        "description": "Incident reports, arrest records, call logs (non-exempt portions)",
        "example_records": [
            "Police incident report for [DATE] at [LOCATION] (report number [#] if known)",
            "Police department call logs from [DATE] to [DATE]",
            "Use of force reports from [DATE RANGE] (redacted per N.J.S.A. 47:1A-1.1)",
            "Annual Uniform Crime Report data for [YEAR]",
        ],
        "notes": "Criminal investigatory records are exempt per N.J.S.A. 47:1A-1.1. Incident reports (non-investigatory) and arrest information are generally public. Victims' information is exempt.",
    },
    "property": {
        "label": "Property/Tax Records",
        "description": "Tax records, assessments, liens, property information",
        "example_records": [
            "Tax assessment records for Block [#], Lot [#]",
            "Property tax collection records for [ADDRESS] from [DATE RANGE]",
            "Tax lien certificates for [YEAR]",
            "Tax appeal records for Block [#], Lot [#]",
        ],
        "notes": "Tax records are generally public. Some may be available directly from the tax assessor or collector without an OPRA request.",
    },
    "communications": {
        "label": "Correspondence & Communications",
        "description": "Official correspondence, emails on municipal business",
        "example_records": [
            "All correspondence between the Borough and [ENTITY] regarding [SUBJECT] from [DATE RANGE]",
            "Emails sent or received by [OFFICIAL TITLE] regarding [SUBJECT] from [DATE RANGE]",
            "Written complaints received by [DEPARTMENT] regarding [SUBJECT] from [DATE RANGE]",
        ],
        "notes": "Advisory, consultative, or deliberative (ACD) material is exempt per N.J.S.A. 47:1A-1.1. Correspondence that constitutes final agency action or policy is generally public.",
    },
    "custom": {
        "label": "Custom/Other Request",
        "description": "Describe the specific records you are seeking",
        "example_records": [],
        "notes": "Be as specific as possible. Identify the department, date range, and type of document. Vague requests (e.g., 'any and all records') may be denied as overbroad.",
    },
}


# ── Pydantic Models ──────────────────────────────────────────────────────────

class OPRAGenerateRequest(BaseModel):
    category: str  # key from RECORD_CATEGORIES
    specific_records: str  # user's description of what they want
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    preferred_format: str = "electronic"  # "electronic", "copies", "inspect"
    requestor_name: str = ""
    requestor_address: str = ""
    requestor_email: str = ""
    requestor_phone: str = ""
    additional_context: str = ""  # any extra details


class OPRAFactCheckRequest(BaseModel):
    request_text: str  # the generated OPRA request to fact-check


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/categories")
async def get_categories():
    """Return available record categories with examples and legal notes."""
    return {
        key: {
            "label": val["label"],
            "description": val["description"],
            "example_records": val["example_records"],
            "notes": val["notes"],
        }
        for key, val in RECORD_CATEGORIES.items()
    }


@router.get("/regulations")
async def get_regulations():
    """Return the full OPRA regulatory reference text."""
    return {
        "regulations": OPRA_REGULATIONS,
        "atlantic_highlands_info": ATLANTIC_HIGHLANDS_INFO,
        "govpilot_url": "https://main.govpilot.com/web/public/2b3162a4-a0f_OPRA-ahadmin?uid=6865&ust=NJ&pu=1&id=1",
        "last_updated": "2024-09-03",
        "amendment": "P.L. 2024, c.16",
    }


@router.post("/generate")
async def generate_opra_request(req: OPRAGenerateRequest):
    """Generate a legally compliant OPRA request letter. Streams the response."""

    category_info = RECORD_CATEGORIES.get(req.category, RECORD_CATEGORIES["custom"])

    date_range_text = ""
    if req.date_range_start and req.date_range_end:
        date_range_text = f"for the period from {req.date_range_start} to {req.date_range_end}"
    elif req.date_range_start:
        date_range_text = f"from {req.date_range_start} to present"
    elif req.date_range_end:
        date_range_text = f"up to and including {req.date_range_end}"

    format_map = {
        "electronic": "electronic copies (email or digital medium)",
        "copies": "paper copies at the statutory rate of $0.05/letter-size page or $0.07/legal-size page per N.J.S.A. 47:1A-5",
        "inspect": "inspection at the municipal offices during regular business hours",
    }
    format_text = format_map.get(req.preferred_format, format_map["electronic"])

    prompt = f"""{OPRA_REGULATIONS}

{ATLANTIC_HIGHLANDS_INFO}

You are an expert municipal records request drafter specializing in New Jersey OPRA law.
Generate a formal, legally compliant OPRA request letter for the following:

REQUESTOR INFORMATION:
- Name: {req.requestor_name or '[REQUESTOR NAME]'}
- Address: {req.requestor_address or '[REQUESTOR ADDRESS]'}
- Email: {req.requestor_email or '[REQUESTOR EMAIL]'}
- Phone: {req.requestor_phone or '[REQUESTOR PHONE]'}

RECORD CATEGORY: {category_info['label']}
SPECIFIC RECORDS REQUESTED: {req.specific_records}
DATE RANGE: {date_range_text or 'Not specified'}
PREFERRED FORMAT: {format_text}
ADDITIONAL CONTEXT: {req.additional_context or 'None'}

INSTRUCTIONS FOR GENERATION:
1. Format as a professional letter addressed to the Records Custodian, Borough of Atlantic Highlands
2. Include the proper legal citation (N.J.S.A. 47:1A-1 et seq.) in the opening
3. Be SPECIFIC about what records are requested - avoid vague language
4. Include the commercial purpose certification (certify this is NOT for commercial purpose)
5. Include the litigation certification (certify no pending litigation)
6. Request the preferred delivery format
7. Note the 7-business-day response deadline per N.J.S.A. 47:1A-5
8. Include a polite but firm note about the requestor's rights under OPRA
9. Add relevant legal notes from the category: {category_info['notes']}
10. If any of the requested records may touch on exempt categories, note which portions
    should be redacted rather than withheld entirely (partial disclosure per N.J.S.A. 47:1A-5)
11. Include today's date: {date.today().strftime('%B %d, %Y')}
12. End with signature block

CITE SPECIFIC STATUTES throughout the letter where applicable (N.J.S.A. sections).
The letter should be professional, legally precise, and ready to submit or paste into the
GovPilot online form at the Atlantic Highlands portal.
"""

    if not GEMINI_API_KEY:
        async def no_key():
            yield f"data: {json.dumps({'type': 'delta', 'content': 'Error: GEMINI_API_KEY is not configured. Please set it in the environment.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(no_key(), media_type="text/event-stream")

    async def stream_generation():
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            config = types.GenerateContentConfig(temperature=0.2, max_output_tokens=8000)

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt, config=config,
                ),
            )

            if response and response.text:
                text = response.text
                chunk_size = 40
                for i in range(0, len(text), chunk_size):
                    yield f"data: {json.dumps({'type': 'delta', 'content': text[i:i+chunk_size]})}\n\n"
                    await asyncio.sleep(0.01)

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"OPRA generation error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(stream_generation(), media_type="text/event-stream")


@router.post("/fact-check")
async def fact_check_opra_request(req: OPRAFactCheckRequest):
    """
    Fact-check an OPRA request using Gemini with grounded search.
    Validates all statutory citations, legal claims, and procedural assertions.
    """
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY is not configured"}

    prompt = f"""{OPRA_REGULATIONS}

You are a New Jersey municipal law fact-checker specializing in OPRA (Open Public Records Act).
Your task is to meticulously verify the following OPRA request for legal accuracy.

=== OPRA REQUEST TO VERIFY ===
{req.request_text}
=== END OF REQUEST ===

FACT-CHECK INSTRUCTIONS:
1. VERIFY every statutory citation (N.J.S.A. section numbers) - are they correct and current
   as of P.L. 2024, c.16?
2. VERIFY all procedural claims (response deadlines, fee amounts, filing procedures)
3. VERIFY the request complies with current OPRA form requirements
4. CHECK if any requested records may fall under OPRA exemptions and flag them
5. VERIFY the commercial purpose and litigation certifications are properly stated
6. CHECK that the request is specific enough (not overbroad per OPRA requirements)
7. VERIFY fee citations match current statutory rates
8. CHECK that the response deadline cited is correct for the type of request

For EACH claim or citation in the request, provide:
- The specific claim or citation
- Whether it is CORRECT, INCORRECT, or NEEDS CLARIFICATION
- The authoritative source (specific N.J.S.A. section or P.L. citation)
- If incorrect, the correct information with proper citation

FORMAT YOUR RESPONSE AS:
## Fact-Check Results

### Overall Assessment
[PASS / PASS WITH NOTES / NEEDS REVISION]

### Citation Verification
[For each citation found in the request]

### Procedural Compliance
[Verification of procedures, deadlines, fees]

### Exemption Warnings
[Any records that may be partially or fully exempt]

### Recommendations
[Any suggested improvements to strengthen the request]

Use the Grounded Search capability to verify any claims against current NJ law if needed.
Be meticulous - every citation must be verified against the actual statute text.
"""

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Use grounded search for fact-checking
        google_search_tool = types.Tool(
            google_search=types.GoogleSearch()
        )

        config = types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=8000,
            tools=[google_search_tool],
        )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=config,
            ),
        )

        result_text = response.text if response and response.text else "Fact-check failed to produce results."

        # Extract grounding metadata if available
        grounding_sources = []
        if response and response.candidates:
            for candidate in response.candidates:
                metadata = getattr(candidate, "grounding_metadata", None)
                if metadata:
                    chunks = getattr(metadata, "grounding_chunks", None) or []
                    for chunk in chunks:
                        web = getattr(chunk, "web", None)
                        if web:
                            grounding_sources.append({
                                "title": getattr(web, "title", ""),
                                "uri": getattr(web, "uri", ""),
                            })

        return {
            "fact_check_result": result_text,
            "grounding_sources": grounding_sources,
            "model": "gemini-2.5-flash",
            "search_grounding": True,
        }

    except Exception as e:
        logger.error(f"OPRA fact-check error: {e}")
        return {"error": str(e)}


@router.post("/generate-pdf-text")
async def generate_pdf_text(req: OPRAGenerateRequest):
    """
    Generate the OPRA request as structured data suitable for PDF generation.
    Returns JSON with all fields needed for a formal OPRA request document.
    """
    category_info = RECORD_CATEGORIES.get(req.category, RECORD_CATEGORIES["custom"])

    date_range_text = ""
    if req.date_range_start and req.date_range_end:
        date_range_text = f"{req.date_range_start} to {req.date_range_end}"
    elif req.date_range_start:
        date_range_text = f"{req.date_range_start} to present"

    format_labels = {
        "electronic": "Electronic copies via email",
        "copies": "Paper copies (statutory fee schedule applies)",
        "inspect": "Inspection at municipal offices",
    }

    return {
        "date": date.today().strftime("%B %d, %Y"),
        "to": {
            "title": "Records Custodian",
            "organization": "Borough of Atlantic Highlands",
            "address": "100 First Avenue, Atlantic Highlands, NJ 07716",
            "phone": "732-291-1444 x3103",
        },
        "from": {
            "name": req.requestor_name or "[REQUESTOR NAME]",
            "address": req.requestor_address or "[REQUESTOR ADDRESS]",
            "email": req.requestor_email or "[REQUESTOR EMAIL]",
            "phone": req.requestor_phone or "[REQUESTOR PHONE]",
        },
        "subject": f"OPRA Request - {category_info['label']}",
        "legal_basis": "N.J.S.A. 47:1A-1 et seq., as amended by P.L. 2024, c.16",
        "records_requested": req.specific_records,
        "record_category": category_info["label"],
        "date_range": date_range_text,
        "delivery_format": format_labels.get(req.preferred_format, "Electronic copies"),
        "certifications": {
            "commercial_purpose": "I certify that this request is NOT for a commercial purpose as defined in N.J.S.A. 47:1A-1.1.",
            "litigation": "I certify that there is no pending litigation related to this request.",
        },
        "response_deadline": "7 business days per N.J.S.A. 47:1A-5",
        "fee_schedule": {
            "letter_size": "$0.05 per page (N.J.S.A. 47:1A-5)",
            "legal_size": "$0.07 per page (N.J.S.A. 47:1A-5)",
            "electronic": "No charge for medium",
        },
        "additional_context": req.additional_context,
        "legal_notes": category_info["notes"],
        "govpilot_url": "https://main.govpilot.com/web/public/2b3162a4-a0f_OPRA-ahadmin?uid=6865&ust=NJ&pu=1&id=1",
    }

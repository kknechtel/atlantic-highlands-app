"""Public pages to crawl for documents. Each seed page is fetched and every
linked document (PDF/Office) is downloaded. Add a page here, not in code.

Kept separate from api/services/scraper/config.py on purpose: that scraper
feeds the public app; this one feeds an evidence store with a custody log.
"""

SOURCES = {
    "hhrsd_boe": {
        "body": "Henry Hudson Regional School District",
        "pages": [
            # BOE agendas & minutes by school year (tridistrict.org Edlio pages)
            "https://www.tridistrict.org/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2749182",  # 2026-2027
            "https://www.tridistrict.org/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2675269",  # 2025-2026
            "https://www.tridistrict.org/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2593279",  # 2024-2025
            "https://www.tridistrict.org/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2593280",  # archive
            "https://www.tridistrict.org/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2580048",  # budget info
            "https://www.tridistrict.org/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2432532",  # BOE main
        ],
    },
    "ahnj": {
        "body": "Borough of Atlantic Highlands",
        "pages": [
            "https://www.ahnj.com/ahnj/Government/Budget%20Information/",
            "https://www.ahnj.com/ahnj/Government/Government%20Records/",
            "https://www.ahnj.com/ahnj/Departments/Finance%20Department/",
            "https://www.ahnj.com/ahnj/Other%20Links/BIDS%20and%20RFPs/",
            "https://www.ahnj.com/ahnj/Agendas/",
            "https://www.ahnj.com/ahnj/Meetings%20and%20Agendas/",
        ],
        # ahnj.com is a directory tree (Budget Information/Annual Audits/, ...):
        # follow child folders of each seed page.
        "follow_children": 2,
    },
    "highlands": {
        "body": "Borough of Highlands",
        "pages": [
            "https://highlandsnj.gov/budget-information/",
            "https://highlandsnj.gov/borough-reports/",
            "https://highlandsnj.gov/bids-and-rfps/",
            "https://highlands-nj.municodemeetings.com/",
        ],
    },
}

# Title/URL patterns -> document class. First match wins; order matters.
DOC_CLASSES = [
    ("bills_list", r"bills?\s*(list|&|and)\s*(claims)?|check\s*register|bill\s*list|vouchers?"),
    ("audit", r"\baudit|\bAMR\b|management\s*report|corrective\s*action|\bACFR\b|\bCAFR\b|comprehensive\s*annual|annual\s*comprehensive"),
    ("disclosure", r"disclosure\s*statement|financial\s*disclosure|\bFDS\b"),
    ("budget", r"budget|\bUFB\b|user[-\s]*friendly|\bAFS\b|annual\s*financial\s*statement|debt\s*statement"),
    ("bid", r"\bbids?\b|\bRFP\b|\bRFQ\b|tabulation|specification"),
    ("minutes", r"minutes"),
    ("agenda", r"agenda|packet"),
    ("resolution", r"resolution"),
]

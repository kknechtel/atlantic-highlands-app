"""
Configuration for Atlantic Highlands Town Repository Scraper.
Adapted for S3 storage (no Box dependency).
"""

# ─── Website sources ────────────────────────────────────────────────
SOURCES = {
    "ahnj": {
        "base_url": "https://www.ahnj.com",
        "description": "Borough of Atlantic Highlands Official Site",
        "pages_to_crawl": [
            # Government & Administration
            "/ahnj/Government",
            "/ahnj/Government/Budget%20Information/",
            "/ahnj/Government/Borough%20Ordinances/",
            "/ahnj/Government/Government%20Records/",
            "/ahnj/Government/Government%20Records/Most%20Referenced%20Ordinances/",
            # "/ahnj/Administration/Council%20Recordings/",  # All audio files, skip
            # Meetings & Agendas (current + archives)
            "/ahnj/Meetings%20and%20Agendas/",
            "/ahnj/Agendas/",
            "/ahnj/Agendas/Archives/",
            "/ahnj/Agendas/Archives/2015/",
            "/ahnj/Agendas/Archives/2016/",
            "/ahnj/Agendas/Archives/2017/",
            "/ahnj/Agendas/Archives/2018/",
            "/ahnj/Agendas/Archives/2019/",
            "/ahnj/Agendas/Archives/2020/",
            "/ahnj/Agendas/Archives/2021/",
            "/ahnj/Agendas/Archives/2022/",
            "/ahnj/Agendas/Archives/2023/",
            "/ahnj/Agendas/Archives/2024/",
            "/ahnj/Agendas/Archives/2025/",
            # Planning Board (key gap!)
            "/ahnj/Departments/Planning%20Board/",
            "/ahnj/Departments/Planning%20Board/Agendas,%20Minutes%20and%20Resolutions/",
            "/ahnj/Departments/Planning%20Board/Planning%20Board%20Agendas%20and%20Minutes/",
            "/ahnj/Departments/Planning%20Board/_Agendas%20and%20Minutes/Archives/",
            # Departments
            "/ahnj/Departments",
            "/ahnj/Departments/Building%20Department/",
            "/ahnj/Departments/Finance%20Department/",
            "/ahnj/Departments/Zoning%20Office/",
            "/ahnj/Departments/Affordable%20Housing/",
            "/ahnj/Departments/Tax%20Assessor/",
            "/ahnj/Departments/Tax%20Collector/",
            "/ahnj/Departments/Police%20Department/",
            "/ahnj/Departments/Fire%20Department/",
            # Other
            "/ahnj/Community",
            "/ahnj/Court",
            "/ahnj/Emergency",
            "/ahnj/Events/",
            "/ahnj/Recreation/",
            "/ahnj/Forms/",
            "/ahnj/Forms/Planning%20and%20Zoning/",
            "/ahnj/Other%20Links/BIDS%20and%20RFPs/",
            "/ahnj/Announcements/",
            # Events calendar - has all meeting schedules with times
            "/ahnj/Upcoming%20Events/",
            "/ahnj/Upcoming%20Events/#gsc.tab=0",
            "/ahnj/Events/",
            "/ahnj/Events/Community%20Events/",
        ],
    },
    "ecode360": {
        "base_url": "https://ecode360.com",
        "description": "Atlantic Highlands Document Repository (Agendas, Minutes, Codes)",
        "pages_to_crawl": [
            "/AT0153/documents/Agendas",
            "/AT0153/documents/Budgets",
            "/AT0153/documents/Comprehensive_Plans",
            "/AT0153/documents/Legislation",
            "/AT0153/documents/Minutes",
            "/AT0153/documents/Misc._Documents",
            "/AT0153/documents/Resolutions",
            "/AT0153",
        ],
    },
    "tridistrict": {
        "base_url": "https://www.tridistrict.org",
        "description": "Henry Hudson Regional School District (Tri-District)",
        "pages_to_crawl": [
            "/",
            # BOE Minutes & Agendas (current)
            "/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2593279",
            # BOE Minutes & Agendas (archives)
            "/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2593280",
            # Board of Education main
            "/apps/pages/index.jsp?uREC_ID=3733528&type=d&pREC_ID=2432532",
        ],
        "school_sites": [
            "https://ahes.tridistrict.org",
            "https://hes.tridistrict.org",
            "https://hhrs.tridistrict.org",
        ],
    },
    "opra": {
        "base_url": "https://opramachine.com",
        "description": "OPRAmachine - Crowdsourced OPRA Requests for Atlantic Highlands",
        "api_url": "https://opramachine.com/body/atlantic_highlands.json",
        "pages_to_crawl": [
            "/body/atlantic_highlands",
        ],
    },
    "police": {
        "base_url": "https://spotcrime.com",
        "description": "Police/Crime Data - SpotCrime, CrimeMapping, Nixle",
        "pages_to_crawl": [
            # SpotCrime
            "https://spotcrime.com/nj/atlantic+highlands",
            # CrimeMapping (may need Selenium)
            "https://www.crimemapping.com/map/nj/atlantichighlands",
            # Nixle/Rave alerts for AH PD
            "https://www.nixle.com/atlantic-highlands-police-department/",
            # AH PD on borough website
            "https://www.ahnj.com/ahnj/Departments/Police%20Department/",
        ],
    },
    "fire": {
        "base_url": "https://web.pulsepoint.org",
        "description": "Fire/EMS Data - PulsePoint, Monmouth County OEM",
        "pages_to_crawl": [
            # PulsePoint web viewer
            "https://web.pulsepoint.org/",
            # AH Fire Department on borough site
            "https://www.ahnj.com/ahnj/Departments/Fire%20Department/",
            # Monmouth County OEM
            "https://www.co.monmouth.nj.us/page.aspx?ID=2434",
        ],
    },
    "county": {
        "base_url": "https://www.monmouthcountyclerk.com",
        "description": "Monmouth County Property Records, Tax Data, Clerk Archives",
        "pages_to_crawl": [
            # County clerk archives for AH
            "https://www.monmouthcountyclerk.gov/archives/record-groups/municipal-records/atlantic-highlands/",
            # Property records search
            "https://oprs.co.monmouth.nj.us/oprs/clerk/clerkhome.aspx?op=basic",
        ],
    },
    "census": {
        "base_url": "https://api.census.gov",
        "description": "US Census ACS Data for Atlantic Highlands",
        "api_config": {
            "state_fips": "34",
            "county_fips": "025",
            "place_fips": "01960",
            "full_fips": "3402501960",
            # Variables: population, median income, median home value, poverty rate, etc.
            "variables": [
                "B01003_001E",  # Total population
                "B19013_001E",  # Median household income
                "B25077_001E",  # Median home value
                "B17001_002E",  # Below poverty level
                "B01002_001E",  # Median age
                "B25001_001E",  # Total housing units
                "B25003_002E",  # Owner occupied
                "B25003_003E",  # Renter occupied
            ],
        },
    },
    "nj_state": {
        "base_url": "https://www.nj.gov",
        "description": "NJ State Data Sources (ACFR, DLGS, Court Opinions)",
        "direct_downloads": [
            # School ACFR reports (Atlantic Highlands SD = 0130, Henry Hudson Regional = 2120)
            # Years 15-24
            "https://www.nj.gov/education/finance/fp/acfr/search/15/0130.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/16/0130.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/17/0130.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/18/0130.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/19/0130.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/20/0130.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/21/0130.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/22/0130.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/23/0130.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/24/0130.pdf",
            # Henry Hudson Regional
            "https://www.nj.gov/education/finance/fp/acfr/search/15/2120.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/16/2120.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/17/2120.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/18/2120.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/19/2120.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/20/2120.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/21/2120.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/22/2120.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/23/2120.pdf",
            "https://www.nj.gov/education/finance/fp/acfr/search/24/2120.pdf",
            # Sea Bright litigation court opinions
            "https://www.njcourts.gov/system/files/court-opinions/2024/a0716-23.pdf",
            "https://www.njcourts.gov/system/files/court-opinions/2025/a_68_24.pdf",
            # Community letters on Sea Bright
            "https://www.ahnj.com/ahnj/Announcements/LettertoCommnity-SeaBrightDecision.pdf",
            "https://highlandsnj.gov/wp-content/uploads/2024/12/Public-Letter-on-Regionalization.pdf",
            "https://highlandsnj.gov/wp-content/uploads/2025/06/Decision-on-Sea-Bright-Amended-Petition-June-2025-2.pdf",
            # Master Plan
            "https://www.ahnj.com/ahnj/Departments/Planning%20Board/Master%20Plan%20(Adopted%202019).pdf",
            "https://www.ahnj.com/ahnj/Departments/Planning%20Board/Zoning%20Map.pdf",
            # Housing Plan
            "https://www.ahnj.com/ahnj/_zumu_user_doc_cache/Housing_Plan_Element_and_Fair_Share_Plan___Atlantic_Highlands___Adopted_June_12_2025.pdf",
        ],
    },
}

# ─── File types to download ────────────────────────────────────────
DOWNLOAD_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".csv", ".txt", ".rtf",
}

# Skip these - too large or not useful as documents
SKIP_EXTENSIONS = {
    ".wav", ".wma", ".mp3", ".mp4", ".avi", ".mov", ".wmv",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico",
}

# ─── Scraper settings ──────────────────────────────────────────────
REQUEST_DELAY = 1.5
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

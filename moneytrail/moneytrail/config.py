"""Thresholds and citations. Verified against primary sources 2026-09-23:
LFN 2025-08 (7/7/2025), LFN 2023-14, P.L.2023, c.30 (Elections Transparency
Act, approved 4/3/2023). Next bid-threshold adjustment due 7/1/2030.
"""
from datetime import date

# Bid thresholds, N.J.S.A. 40A:11-3 (LPCL) / 18A:18A-3 (PSCL). Effective-dated:
# (effective_from, {(law, has_qpa): amount}). Pre-7/1/2020 no-QPA values are
# not modeled; those dates use the 2020 row for no-QPA units.
BID_THRESHOLDS = [
    (date(1900, 1, 1), {("LPCL", True): 40_000, ("PSCL", True): 40_000,
                        ("LPCL", False): 17_500, ("PSCL", False): 32_000}),
    (date(2020, 7, 1), {("LPCL", True): 44_000, ("PSCL", True): 44_000,
                        ("LPCL", False): 17_500, ("PSCL", False): 32_000}),
    (date(2025, 7, 1), {("LPCL", True): 53_000, ("PSCL", True): 53_000,
                        ("LPCL", False): 17_500, ("PSCL", False): 39_000}),
]
# Most NJ units have a QPA. Assuming one uses the higher threshold, which
# means fewer flags. Set has_qpa in public_bodies to override.
DEFAULT_HAS_QPA = True


def bid_threshold(law, has_qpa, on):
    amt = None
    for eff, table in BID_THRESHOLDS:
        if on >= eff:
            amt = table[(law, has_qpa)]
    return amt


# Pay-to-play, N.J.S.A. 19:44A-20.4 (counties) / 20.5 (municipalities), as
# amended by P.L.2023 c.30: no contract > $17,500 other than via fair and
# open process (public bidding now counts) if the vendor made a *reportable*
# contribution to a *candidate committee* of an official of that body in the
# preceding year, or during the contract term. Boards of education, fire
# districts and authorities are NOT covered by 20.4/20.5; they get the
# 19:44A-20.26 disclosure requirement instead (contracts > $17,500 not publicly
# bid; contribution list filed >= 10 days before award).
P2P_CONTRACT_MIN = 17_500
ETA_DATE = date(2023, 4, 3)
# "Reportable" under 19:44A-8: > $300 before c.30, > $200 after.


def p2p_reportable_min(on):
    return 200 if on >= ETA_DATE else 300


P2P_LOOKBACK_DAYS = 365
# The ban runs for the contract term. Awards rarely carry an end date, so a
# one-year term is assumed.
P2P_LOOKAHEAD_DAYS = 365
P2P_BODY_TYPES = {"municipal": "N.J.S.A. 19:44A-20.5", "county": "N.J.S.A. 19:44A-20.4"}
DISCLOSURE_2026 = "N.J.S.A. 19:44A-20.26"

# N.J.S.A. 19:44A-20.27: Form BE annual disclosure required for a business
# entity receiving >= $50,000 in aggregate from public entities in a year.
BE_ANNUAL_MIN = 50_000

# Cumulative change orders > 20% of the original need the N.J.A.C. 5:30-11.9
# procedure (local units). Boards of education: N.J.A.C. 6A:23A-21.1 applies
# 5:30-11; capital projects > 20% need DOE approval under 6A:26-4.9.
CHANGE_ORDER_PCT = 0.20

# "Just under threshold" band for award splitting (fraction of the bid
# threshold in effect on the award date).
SPLIT_BAND_LOW = 0.80
SPLIT_WINDOW_DAYS = 365

REPEAT_NONCOMPETITIVE_MIN = 2
REPEAT_NONCOMPETITIVE_DAYS = 730

SHARED_ADDRESS_MIN_VENDORS = 3

OVERTIME_RATIO = 0.50

# Entity resolution. token_sort_ratio scores (0-100).
ER_NAME_ALONE = 93        # name match strong enough on its own
ER_NAME_WITH_ZIP = 86     # needs same zip5 or same normalized address
ER_NAME_WITH_ADDR = 75    # needs same normalized street address

NONCOMPETITIVE_TYPES = ("sole_source", "emergency")
COMPETITIVE_TYPES = ("bid", "state_contract", "coop", "competitive_contracting")
BID_EXEMPT_TYPES = ("professional_services", "extraordinary_unspecifiable", "shared_services")

# Statute cited per body type.
BID_LAW = {
    "school": "N.J.S.A. 18A:18A-3 (Public School Contracts Law)",
    "default": "N.J.S.A. 40A:11-3 (Local Public Contracts Law)",
}
CHANGE_ORDER_RULE = {
    "school": "N.J.A.C. 6A:23A-21.1 / 5:30-11; capital projects N.J.A.C. 6A:26-4.9",
    "default": "N.J.A.C. 5:30-11.3, 11.9",
}
ETHICS_LAW = {
    "school": "School Ethics Act, N.J.S.A. 18A:12-24",
    "default": "Local Government Ethics Law, N.J.S.A. 40A:9-22.5",
}

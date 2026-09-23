"""Thresholds. Statutory numbers change by Local Finance Notice / statute
amendment. Verify against the current LFN before relying on any flag."""

# N.J.S.A. 40A:11-3 bid threshold. $44,000 without a QPA, $53,000 with one
# (eff. 7/1/2020). Adjusted every 5 years; confirm the current LFN.
BID_THRESHOLD = 44_000
BID_THRESHOLD_QPA = 53_000

# Pay-to-play, N.J.S.A. 19:44A-20.5: contracts > $17,500 awarded other than
# via fair-and-open process; contributions > $300 in the prior year.
P2P_CONTRACT_MIN = 17_500
P2P_CONTRIBUTION_MIN = 300
P2P_LOOKBACK_DAYS = 365
# Contributions shortly after an award are also worth a look (quid pro quo).
P2P_LOOKAHEAD_DAYS = 90

# N.J.S.A. 19:44A-20.27: Form BE annual disclosure required for a business
# entity receiving >= $50,000 in aggregate from public entities in a year.
BE_ANNUAL_MIN = 50_000

# N.J.A.C. 5:30-11: cumulative change orders > 20% of original need
# additional certification/justification.
CHANGE_ORDER_PCT = 0.20

# "Just under threshold" band for award splitting.
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

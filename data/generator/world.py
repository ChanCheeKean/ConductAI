"""Static world: issuer, products, offers, sites, teams, colleagues, workstations, cities, names, code tables."""
from __future__ import annotations

from common import Ctx, local_to_utc
from derived import BANK_HOLIDAYS

ISSUER = "Copperlake Bank, N.A."

# ---------------------------------------------------------------- products and offers
PRODUCTS = {
    "EVERYDAY_CASH": dict(name="Everyday Cash Visa", annual_fee="0.00", purchase_apr="24.49", rewards_unit="cash_back",
                          doc="CLB-PRD-EVERYDAY-CASH@v4"),
    "VOYAGER": dict(name="Voyager Visa Signature", annual_fee="95.00", purchase_apr="24.49", rewards_unit="miles",
                    doc="CLB-PRD-VOYAGER@v5"),
    "SUMMIT": dict(name="Summit Visa Infinite", annual_fee="450.00", purchase_apr="25.99", rewards_unit="miles",
                   doc="CLB-PRD-SUMMIT@v3"),
    "FOUNDATION": dict(name="Foundation Secured Visa", annual_fee="0.00", purchase_apr="28.49", rewards_unit="cash_back",
                       doc="CLB-PRD-FOUNDATION@v2"),
}
ADDONS = {
    "CARDSHIELD": dict(name="CardShield payment protection", pricing="$0.89 per $100 of ending statement balance",
                       doc="CLB-PRD-CARDSHIELD@v3", script="CLB-CHC-ADDON-CS@v3"),
    "CREDITWATCH_PLUS": dict(name="CreditWatch Plus", pricing="$14.99 per month", monthly_fee="14.99",
                             doc="CLB-PRD-CREDITWATCH@v2", script="CLB-CHC-ADDON-CW@v2"),
}
OFFER_CODES = [
    # offer_code, offer_type, promo_apr, promo_months, fee_rate, eligibility note
    ("OFR-BT-12-3", "BT", "0.00", 12, "3.00", "all open accounts in good standing"),
    ("OFR-BT-15-3", "BT", "0.00", 15, "3.00", "promotional segment only"),
    ("OFR-BT-15-5", "BT", "0.00", 15, "5.00", "all open accounts in good standing"),
    ("OFR-CLI", "CLI", "", "", "", "customer-requested credit line increase"),
    ("OFR-CLI-PS", "CLI_PRESCREEN", "", "", "", "prescreened firm offer; instance id OFR-CLI-PS-<n>"),
    ("OFR-FLEX-12", "FLEX", "", 12, "1.72", "monthly plan fee % of principal; not for HARDSHIP_ACTIVE accounts"),
    ("OFR-PC", "PRODUCT_CHANGE", "", "", "", "product change between card products"),
    ("OFR-ADDON-CS", "ADDON", "", "", "", "CardShield"),
    ("OFR-ADDON-CW", "ADDON", "", "", "", "CreditWatch Plus"),
    ("OFR-RET-CREDIT", "RETENTION", "", "", "", "retention statement credit"),
]
FEE_SCHEDULE = [
    ("LATE_FEE", "32.00", "CLB-PRD-CARDHOLDER-AGREEMENT@v9 §4.2"),
    ("RETURNED_PAYMENT_FEE", "29.00", "CLB-PRD-CARDHOLDER-AGREEMENT@v9 §4.3"),
    ("ANNUAL_FEE_VOYAGER", "95.00", "CLB-PRD-VOYAGER@v5 §1"),
    ("ANNUAL_FEE_SUMMIT", "450.00", "CLB-PRD-SUMMIT@v3"),
    ("CREDITWATCH_PLUS_MONTHLY", "14.99", "CLB-PRD-CREDITWATCH@v2 §2.1"),
    ("CARDSHIELD_PER_100_ENDING_BALANCE", "0.89", "CLB-PRD-CARDSHIELD@v3 §2.1"),
    ("FLEX_12M_MONTHLY_RATE_PCT", "1.72", "CLB-PRD-FLEX@v2 §2.1"),
]
REWARDS_CONVERSION_CENTS_PER_MILE = "0.5"

# ---------------------------------------------------------------- sites, teams, colleagues
SITES = {
    "TEMPE": dict(city="Tempe", state="AZ", timezone="America/Phoenix", ws_prefix="WS-T"),
    "SAN_ANTONIO": dict(city="San Antonio", state="TX", timezone="America/Chicago", ws_prefix="WS-S"),
}
# team_id: (site, supervisor, agents, queue types, languages)
TEAMS = {
    "T-TMP-1": ("TEMPE", "COL-3100", ["COL-3108", "COL-3112", "COL-3122", "COL-3131", "COL-3141", "COL-3150",
                                      "COL-3163", "COL-3177", "COL-3190", "COL-3199"], ["general"], "en"),
    "T-TMP-2": ("TEMPE", "COL-5500", ["COL-5503", "COL-5510", "COL-5512", "COL-5518", "COL-5520", "COL-5526",
                                      "COL-5530", "COL-5535", "COL-5541", "COL-5547"], ["general", "retention"], "en"),
    "T-TMP-3": ("TEMPE", "COL-4400", ["COL-4403", "COL-4409", "COL-4412", "COL-4417", "COL-4421", "COL-4425",
                                      "COL-4430", "COL-4436", "COL-4442"], ["general"], "en"),
    "T-SAT-1": ("SAN_ANTONIO", "COL-7700", ["COL-7705", "COL-7708", "COL-7712", "COL-7716", "COL-7721", "COL-7724",
                                            "COL-7730", "COL-7735", "COL-7741", "COL-7748"], ["general", "bilingual"], "en|es"),
    "T-SAT-2": ("SAN_ANTONIO", "COL-6600", ["COL-6604", "COL-6611", "COL-6618", "COL-6622", "COL-6630", "COL-6637",
                                            "COL-6645", "COL-6651", "COL-6658"], ["general"], "en"),
    "T-SAT-3": ("SAN_ANTONIO", "COL-8800", ["COL-8805", "COL-8813", "COL-8819", "COL-8826", "COL-8832", "COL-8840",
                                            "COL-8847", "COL-8853", "COL-8861", "COL-8870"], ["general", "hardship"], "en"),
}
EXTRA_BILINGUAL = {"COL-8813"}
# Workstation clock offsets (seconds; positive = workstation clock fast). Measured 2026-10-01.
SPECIAL_WORKSTATIONS = {"COL-4417": ("WS-T-118", 9), "COL-3122": ("WS-T-104", 0), "COL-3141": ("WS-T-109", -2)}
CHAT_CAPABLE_TEAMS = {"T-SAT-1", "T-SAT-2", "T-SAT-3", "T-TMP-2"}

# ---------------------------------------------------------------- customer geography and names
CITIES = [
    # city, state, zip3, timezone, area code, weight
    ("Des Moines", "IA", "503", "America/Chicago", "515", 5), ("Tulsa", "OK", "741", "America/Chicago", "918", 5),
    ("Mesa", "AZ", "852", "America/Phoenix", "480", 6), ("Phoenix", "AZ", "850", "America/Phoenix", "602", 10),
    ("Tucson", "AZ", "857", "America/Phoenix", "520", 5), ("San Antonio", "TX", "782", "America/Chicago", "210", 10),
    ("El Paso", "TX", "799", "America/Denver", "915", 5), ("Houston", "TX", "770", "America/Chicago", "713", 9),
    ("Dallas", "TX", "752", "America/Chicago", "214", 8), ("Albuquerque", "NM", "871", "America/Denver", "505", 4),
    ("Denver", "CO", "802", "America/Denver", "303", 6), ("Omaha", "NE", "681", "America/Chicago", "402", 4),
    ("Kansas City", "MO", "641", "America/Chicago", "816", 5), ("Las Vegas", "NV", "891", "America/Los_Angeles", "702", 6),
    ("Los Angeles", "CA", "900", "America/Los_Angeles", "213", 8), ("Chicago", "IL", "606", "America/Chicago", "312", 7),
    ("Atlanta", "GA", "303", "America/New_York", "404", 5), ("Columbus", "OH", "432", "America/New_York", "614", 4),
]
FIRST_NAMES = ["Avery", "Bellamy", "Corinne", "Dalton", "Evelyn", "Fletcher", "Gwen", "Harlan", "Iris", "Jonah",
               "Keira", "Leland", "Maren", "Nolan", "Opal", "Porter", "Quinn", "Rosalind", "Silas", "Tessa",
               "Ulysses", "Vera", "Wade", "Yvonne", "Zane", "Amos", "Beatrix", "Cyrus", "Delia", "Emmett",
               "Faye", "Grady", "Hollis", "Ingrid", "Jasper", "Lorna", "Milo", "Nadia", "Otis", "Priya",
               "Reed", "Sloane", "Tobias", "Wendell", "Hazel", "Colby", "Darla", "Ronan", "Kendra", "Marcus"]
LAST_NAMES = ["Ashford", "Brennan", "Calloway", "Dunmore", "Ellery", "Faraday", "Garrity", "Holloway", "Ingram",
              "Jessop", "Kincaid", "Lockhart", "Merriweather", "Norquist", "Oakes", "Prescott", "Radley", "Sterling",
              "Thorne", "Underwood", "Vance", "Whitaker", "Yates", "Ambrose", "Blakely", "Corwin", "Draper", "Easton",
              "Fenwick", "Galloway", "Hartigan", "Kessler", "Lindqvist", "Marlowe", "Pendleton", "Quimby", "Rowley",
              "Sayers", "Tillman", "Wexford"]
FIRST_NAMES_ES = ["Alejandra", "Benicio", "Catalina", "Diego", "Esperanza", "Fernando", "Graciela", "Héctor",
                  "Inés", "Joaquín", "Lucía", "Mateo", "Nayeli", "Octavio", "Paloma", "Ramiro", "Soledad", "Teodoro",
                  "Valeria", "Ximena"]
LAST_NAMES_ES = ["Aguilar", "Barrera", "Cisneros", "Delgado", "Escobedo", "Fuentes", "Galindo", "Herrera", "Ibarra",
                 "Jaramillo", "Lozano", "Montoya", "Navarro", "Ochoa", "Pineda", "Quintero", "Rosales", "Salazar",
                 "Treviño", "Villarreal"]

# ---------------------------------------------------------------- code tables
GLOSSARY_CODES = [
    ("MC-01", "Pressure / excessive rebuttals after a clear decline", "judgment"),
    ("MC-02", "Enrollment or sale without affirmative, informed consent", "bright_line"),
    ("MC-03", "Misrepresentation of product terms", "bright_line"),
    ("MC-04", "Omission or unclear delivery of a required disclosure", "bright_line"),
    ("MC-05", "Inaccurate credit-reporting, score or inquiry information", "bright_line"),
    ("MC-06", "Leveraging a servicing, cancellation or fee request to secure a sale; failing to honor a cancellation", "judgment"),
    ("MC-07", "Sale in a prohibited context", "bright_line"),
    ("MC-08", "Undisclosed product switching", "bright_line"),
    ("MC-09", "Sale to a customer in a protected situation", "judgment"),
    ("MC-10", "Misinformation about or obstruction of customer rights", "judgment"),
    ("MC-11", "Inaccurate records", "bright_line"),
]
DISPOSITION_CODES = [
    ("GEN_INQUIRY", "General inquiry"), ("BALANCE_PAYMENT", "Balance or payment question"),
    ("FEE_INQUIRY", "Fee question"), ("FEE_WAIVER", "Fee waived"), ("CARD_REPLACEMENT", "Lost/stolen/replacement card"),
    ("REWARDS", "Rewards inquiry or redemption"), ("PRODUCT_INFO", "Product information"),
    ("CLI_REQUEST", "Credit line increase request"), ("SALE_BT", "Balance transfer sale"),
    ("SALE_ADDON", "Add-on enrollment"), ("SALE_FLEX", "Flex Installments plan"), ("PRODUCT_CHANGE", "Product change"),
    ("RETENTION_SAVE", "Retention: account kept"), ("ACCOUNT_CLOSED", "Account closed"),
    ("HARDSHIP", "Hardship program"), ("DISPUTE_INTAKE", "Billing dispute intake"),
    ("PROFILE_UPDATE", "Address or profile update"), ("COMPLAINT", "Complaint logged"),
    ("SCRA_REFERRAL", "SCRA benefits review opened"), ("CALLBACK_SCHEDULED", "Callback scheduled"),
]
IVR_INTENTS = ["balance_payment", "fee_question", "lost_card", "rewards", "product_question", "credit_line_increase",
               "balance_transfer", "close_account", "hardship", "dispute", "address_profile", "other"]
CALLBACK_PURPOSES = ["balance_transfer_offer", "replacement_card_status", "credit_line_increase", "dispute_followup",
                     "hardship_followup", "payment_arrangement", "rewards_question"]
ASR_MODELS = [
    ("en-US-general", "en", "English general telephony model"),
    ("es-US-general", "es", "Spanish (US) telephony model"),
    ("none", "", "Chat and secure message: exact text, no ASR"),
]
MONITORING_SLA = [
    ("CLB-SOP-CRM-001@v4", 15, "later of interaction date and selection/trigger date", "2025-03-03", "2026-08-31"),
    ("CLB-SOP-CRM-001@v5", 10, "later of interaction date and selection/trigger date", "2026-09-01", ""),
]


def workstation(colleague_id: str) -> tuple:
    if colleague_id in SPECIAL_WORKSTATIONS:
        return SPECIAL_WORKSTATIONS[colleague_id]
    team = team_of(colleague_id)
    prefix = SITES[TEAMS[team][0]]["ws_prefix"]
    num = 200 + int(colleague_id[-4:]) % 700
    offset = (int(colleague_id[-2:]) * 7) % 5 - 2    # -2..+2 s of ordinary drift
    return f"{prefix}-{num}", offset


def team_of(colleague_id: str) -> str:
    for team_id, (_, sup, agents, _, _) in TEAMS.items():
        if colleague_id == sup or colleague_id in agents:
            return team_id
    raise KeyError(colleague_id)


def site_tz(colleague_id: str) -> str:
    return SITES[TEAMS[team_of(colleague_id)][0]]["timezone"]


def is_bilingual(colleague_id: str) -> bool:
    return TEAMS[team_of(colleague_id)][4] == "en|es" or colleague_id in EXTRA_BILINGUAL


def build(ctx: Ctx):
    """Teams and colleagues (64). Hire dates are deterministic from the ID."""
    for team_id, (site, sup, agents, queues, _) in TEAMS.items():
        ctx.add("teams", dict(team_id=team_id, site=site, supervisor_id=sup, queue_types="|".join(queues),
                              available_at="2025-01-01T00:00:00Z"))
        for cid in [sup] + agents:
            n = int(cid[-4:])
            hire = f"{2016 + n % 9}-{1 + n % 12:02d}-{1 + n % 27:02d}"
            ctx.add("colleagues", dict(
                colleague_id=cid, role="supervisor" if cid == sup else "agent", team_id=team_id, site=site,
                site_timezone=SITES[site]["timezone"], hire_date=hire,
                languages="en|es" if is_bilingual(cid) else "en",
                licensed_products="BT|CLI|FLEX|ADDON|PRODUCT_CHANGE|RETENTION",
                available_at=local_to_utc(hire, "09:00:00", SITES[site]["timezone"])))


def reference_tables() -> dict:
    """name -> (header, rows) for data/generated/reference/*.csv."""
    colleagues = [c for _, sup, agents, _, _ in TEAMS.values() for c in [sup] + agents]
    return {
        "glossary_codes": (["code", "category", "typical_type"], GLOSSARY_CODES),
        "disposition_codes": (["code", "meaning"], DISPOSITION_CODES),
        "offer_codes": (["offer_code", "offer_type", "promo_apr", "promo_months", "fee_rate", "eligibility"], OFFER_CODES),
        "product_catalog": (["product_code", "name", "annual_fee", "purchase_apr", "rewards_unit", "fact_sheet"],
                            [(k, v["name"], v["annual_fee"], v["purchase_apr"], v["rewards_unit"], v["doc"])
                             for k, v in PRODUCTS.items()] +
                            [(k, v["name"], "", "", "", v["doc"]) for k, v in ADDONS.items()]),
        "fee_schedule": (["fee", "amount", "source"], FEE_SCHEDULE),
        "bank_holidays_2026": (["date", "holiday"], sorted(BANK_HOLIDAYS.items())),
        "site_timezones": (["site", "city", "state", "timezone", "observes_dst"],
                           [(k, v["city"], v["state"], v["timezone"], "false" if k == "TEMPE" else "true")
                            for k, v in SITES.items()]),
        "desktop_clock_offsets": (["workstation_id", "colleague_id", "offset_seconds", "measured_at"],
                                  sorted((workstation(c)[0], c, workstation(c)[1], "2026-10-01T15:00:00Z")
                                         for c in colleagues)),
        "asr_models": (["asr_model", "language", "description"], ASR_MODELS),
        "monitoring_sla": (["policy_version", "business_days", "clock_start_rule", "effective_from", "effective_to"],
                           MONITORING_SLA),
        "ivr_intents": (["ivr_intent"], [(x,) for x in IVR_INTENTS]),
        "callback_purposes": (["purpose"], [(x,) for x in CALLBACK_PURPOSES]),
    }

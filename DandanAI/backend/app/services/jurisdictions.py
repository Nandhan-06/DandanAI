"""Jurisdiction hierarchy and the 12 coverage layers for the Bharat Legal Research Engine."""
STATES = ["Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
          "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
          "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"]
UTS = ["Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
       "Ladakh", "Lakshadweep", "Puducherry"]
HIGH_COURTS = ["Allahabad", "Andhra Pradesh", "Bombay", "Calcutta", "Chhattisgarh", "Delhi", "Gauhati", "Gujarat", "Himachal Pradesh",
               "Jammu & Kashmir and Ladakh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Madras", "Manipur", "Meghalaya",
               "Orissa", "Patna", "Punjab and Haryana", "Rajasthan", "Sikkim", "Telangana", "Tripura", "Uttarakhand"]
LAYERS = [
    ("constitution_central_acts", "Constitution and Central Acts"),
    ("amendments_subordinate", "Amendments, ordinances and subordinate legislation"),
    ("state_uts_legislation", "State and UT legislation (28 States, 8 UTs)"),
    ("state_rules_notifications", "State amendments, rules, regulations, notifications, circulars"),
    ("supreme_court", "Supreme Court"),
    ("high_courts", "High Courts and benches"),
    ("district_courts", "District and subordinate courts"),
    ("tribunals", "National and State tribunals / appellate tribunals"),
    ("regulators", "Regulators and statutory authorities"),
    ("municipal_bylaws", "Municipal and local-body bylaws"),
    ("development_regulations", "Development regulations and local notifications"),
    ("treaties_specialised", "Applicable treaties and specialised instruments"),
]
LAYER_KEYS = [k for k, _ in LAYERS]


def all_jurisdictions() -> list[str]:
    return ["India"] + STATES + UTS


def applicable(jurisdiction: str | None) -> list[str]:
    """A matter in a State is governed by Central (India) + that State's instruments."""
    if not jurisdiction or jurisdiction.strip().lower() in ("india", "central", "all"):
        return ["India"]
    j = jurisdiction.strip()
    for name in STATES + UTS:
        if name.lower() == j.lower() or name.lower() in j.lower():
            return ["India", name]
    return ["India", j]

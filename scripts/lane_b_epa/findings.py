"""Interpret *reported* environmental source measures without producing risk scores.

Numbers are returned as exact decimal text and retain the original source units.
Never aggregate across chemicals, reporting years or unlike money categories.
"""
from decimal import Decimal, InvalidOperation

GRAM_KG=Decimal("0.001")
POUND_KG=Decimal("0.45359237")
NOT_REPORTED=frozenset(("", "NA", "N/A", "NOT REPORTED", "UNKNOWN", "-", "--", "NONE"))

def source_decimal(value,allow_negative=False):
    if value is None:return {"value":None,"state":"not_reported"}
    raw=str(value).strip()
    if raw.upper() in NOT_REPORTED:return {"value":None,"state":"not_reported"}
    if len(raw)>80:return {"value":None,"state":"invalid_numeric"}
    try:
        cleaned=raw.replace(",","")
        amount=Decimal(cleaned)
    except (InvalidOperation,ValueError):
        return {"value":None,"state":"invalid_numeric"}
    if not amount.is_finite():
        return {"value":None,"state":"invalid_numeric"}
    if amount<0 and not allow_negative:
        return {"value":None,"state":"negative_value_requires_review"}
    if amount==0:return {"value":"0","state":"reported_zero"}
    return {"value":format(amount,"f"),"state":"reported_numeric"}

def tri_release_measure(row,field):
    """Numeric TRI release, source units, and optional exact kg for a *single chemical*."""
    original=row.get(field)
    measure=source_decimal(original)
    unit=(row.get("50_UNIT_OF_MEASURE") or "").strip()
    measure.update({"source_field":field,"original_text":original,"reported_unit":unit or None,
        "measure_scope":"TRI one chemical/reporting-year observation; not a site exposure or insurance loss"})
    if measure["value"] is None:
        measure["kilograms"]=None
        return measure
    factor={"Grams":GRAM_KG,"Pounds":POUND_KG}.get(unit)
    if factor is None:
        measure["kilograms"]=None
        measure["state"]="numeric_unrecognized_unit"
    else:
        measure["kilograms"]=format(Decimal(measure["value"])*factor,"f")
    return measure

def tri_reported_measures(row):
    return {
        "on_site_release":tri_release_measure(row,"65_ON_SITE_RELEASE_TOTAL"),
        "off_site_release":tri_release_measure(row,"88_OFF_SITE_RELEASE_TOTAL"),
        "total_release":tri_release_measure(row,"107_TOTAL_RELEASES"),
        "unit_conversion_rule":"Grams x 0.001, Pounds x 0.45359237 for each chemical separately; no cross-chemical aggregation"
    }

def rcra_enforcement_measures(row):
    categories=("PMP_AMOUNT","FMP_AMOUNT","FSC_AMOUNT","SCR_AMOUNT")
    return {field:{**source_decimal(row.get(field)),"source_unit":"source_reported_dollars_not_independently_verified",
                   "original_text":row.get(field),
                   "aggregation_rule":"Do not sum distinct RCRA enforcement amount categories without EPA semantics"}
            for field in categories if field in row}

def echo_summary_measures(row):
    return {"reported_total_penalties":{**source_decimal(row.get("FAC_TOTAL_PENALTIES")),
             "source_unit":"source_reported_dollars_not_independently_verified",
             "is_aggregate_facility_summary":True},
            "reported_inspection_count":source_decimal(row.get("FAC_INSPECTION_COUNT")),
            "reported_formal_action_count":source_decimal(row.get("FAC_FORMAL_ACTION_COUNT")),
            "reported_compliance_status":row.get("FAC_COMPLIANCE_STATUS") or None,
            "reported_snc_flag":row.get("FAC_SNC_FLG") or None,
            "interpretation":"ECHO wide export is regulator summary; flags are not independently verified incident counts or loss claims"}

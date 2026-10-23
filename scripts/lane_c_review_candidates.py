"""Conservative cross-agency *review candidates*, never verified physical-site links.

Exact normalized publisher-reported company+city+state+incident date across
CSB and NRC is one audit cue, not independent proof of a shared incident.
"""
from __future__ import annotations
from collections import Counter,defaultdict
import json
import re
import sqlite3
import unicodedata

# Official US abbreviations for textual equivalent match only. No geocoding.
STATES = """ALABAMA AL ALASKA AK ARIZONA AZ ARKANSAS AR CALIFORNIA CA
COLORADO CO CONNECTICUT CT DELAWARE DE FLORIDA FL GEORGIA GA HAWAII HI
IDAHO ID ILLINOIS IL INDIANA IN IOWA IA KANSAS KS KENTUCKY KY
LOUISIANA LA MAINE ME MARYLAND MD MASSACHUSETTS MA MICHIGAN MI
MINNESOTA MN MISSISSIPPI MS MISSOURI MO MONTANA MT NEBRASKA NE
NEVADA NV NEW_HAMPSHIRE NH NEW_JERSEY NJ NEW_MEXICO NM NEW_YORK NY
NORTH_CAROLINA NC NORTH_DAKOTA ND OHIO OH OKLAHOMA OK OREGON OR
PENNSYLVANIA PA RHODE_ISLAND RI SOUTH_CAROLINA SC SOUTH_DAKOTA SD
TENNESSEE TN TEXAS TX UTAH UT VERMONT VT VIRGINIA VA WASHINGTON WA
WEST_VIRGINIA WV WISCONSIN WI WYOMING WY DISTRICT_OF_COLUMBIA DC
PUERTO_RICO PR VIRGIN_ISLANDS VI""".split()
STATE_MAP = dict(zip(STATES[::2], STATES[1::2]))
for code in list(STATE_MAP.values()):
    STATE_MAP[code]=code

def normalized_text(value):
    if value is None:
        return ""
    text=unicodedata.normalize("NFKD",str(value)).encode("ascii","ignore").decode().upper()
    return " ".join(re.findall(r"[A-Z0-9]+",text))

def state_code(value):
    return STATE_MAP.get(normalized_text(value).replace(" ","_"),"")

def can_match(key):
    day,state,city,name=key
    generic={"UNKNOWN","N A","NOT AVAILABLE","NONE","UNIDENTIFIED"}
    return bool(day and state and city and len(name)>=8 and name not in generic
                and len(city)>=3 and city not in generic)

def candidate_key(row):
    try:
        payload=json.loads(row["source_json"])
    except (KeyError,TypeError,ValueError) as e:
        raise ValueError("Source JSON is not a validated incident row") from e
    return (row["incident_date"] or "", state_code(row["state"] or ""),
            normalized_text(row["city"]), normalized_text(payload.get("company_as_reported")))

def build_review_candidates(db_path):
    with sqlite3.connect(db_path) as db:
        db.row_factory=sqlite3.Row
        db.execute("""CREATE TABLE IF NOT EXISTS lane_c_review_candidates(
          nrc_source TEXT NOT NULL,
          nrc_source_id TEXT NOT NULL,
          csb_source TEXT NOT NULL,
          csb_source_id TEXT NOT NULL,
          match_rule TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status='review_candidate_not_corrob'),
          PRIMARY KEY(nrc_source,nrc_source_id,csb_source,csb_source_id)
        ) WITHOUT ROWID""")
        csb=list(db.execute("SELECT * FROM source_incidents WHERE source='csb'"))
        nrc=list(db.execute("SELECT * FROM source_incidents WHERE source='nrc' OR source LIKE 'nrc_%'"))
        lookup=defaultdict(list)
        for row in csb:
            key=candidate_key(row)
            if can_match(key):
                lookup[key].append(row)
        found=0
        for row in nrc:
            key=candidate_key(row)
            if not can_match(key):
                continue
            for other in lookup.get(key,()):
                db.execute("""INSERT OR IGNORE INTO lane_c_review_candidates(
                    nrc_source,nrc_source_id,csb_source,csb_source_id,match_rule,status
                    ) VALUES(?,?,?,?,?,?)""",
                    (row["source"],row["source_id"],other["source"],other["source_id"],
                     "exact_reported_day_city_state_company_text",
                     "review_candidate_not_corrob"))
                found+=1
        counts=db.execute("SELECT COUNT(*), COUNT(DISTINCT csb_source_id) FROM lane_c_review_candidates").fetchone()
        if found < counts[0]:
            raise ValueError("Candidate build count inconsistency")
        db.commit()
        assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        return {
            "matching_rule":"exact company text + date + city + normalized US state",
            "status":"NEEDS_HUMAN_REVIEW_NOT_VERIFIED",
            "review_candidate_pairs":counts[0],
            "distinct_csb_report_candidates":counts[1],
            "verified_shared_events":0, "independent_outcomes_corrob":0,
            "insured_physical_site_links":0,
            "limitation":"Same reported attributes across agencies are not proof of same accident or physical facility; no automatic merges or claims"
        }

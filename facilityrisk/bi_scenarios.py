"""Underwriter-controlled business-interruption hypotheses, never insurance recoveries.

Financial outputs are conditional arithmetic on analyst-supplied assumptions,
not sourced property loss, premium, catastrophe expected loss, paid claim or
coverage determination. Keep these in the authenticated private workspace.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
import uuid

from .intelligence import audit

SCHEMA="""
CREATE TABLE IF NOT EXISTS interruption_scenarios (
 id TEXT PRIMARY KEY,
 facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 scenario_name TEXT NOT NULL,
 interruption_cause TEXT NOT NULL,
 affected_dependency TEXT NOT NULL,
 scenario_description TEXT NOT NULL DEFAULT '',
 assumption_basis TEXT NOT NULL DEFAULT '',
 reference_url TEXT NOT NULL DEFAULT '',
 gross_outage_days REAL NOT NULL,
 margin_at_risk_daily_usd REAL NOT NULL,
 outage_mitigation_fraction REAL NOT NULL DEFAULT 0,
 recovery_ramp_days REAL NOT NULL DEFAULT 0,
 recovery_average_capacity REAL NOT NULL DEFAULT 1,
 extra_expense_usd REAL,
 stock_spoilage_usd REAL,
 property_repair_usd REAL,
 revision INTEGER NOT NULL DEFAULT 1,
 entered_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 changed_by TEXT NOT NULL,
 changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bi_scenarios_facility ON interruption_scenarios(facility_id,changed_at);
"""

CAUSES=frozenset({'flood','windstorm','wildfire','earthquake',
    'utility_failure','supplier_disruption','civil_authority',
    'geopolitical','cyber','operational','other'})
DEPENDENCIES=frozenset({'grid_power','water','natural_gas','telecom',
    'supplier','customer','transport','access','equipment','staffing','other'})
COVERAGE_LOOKUP={
 'flood':['flood','bi','extra_expense','parametric_flood'],
 'windstorm':['windstorm','bi','extra_expense','parametric_wind'],
 'wildfire':['wildfire','bi','extra_expense','parametric_wildfire'],
 'earthquake':['earthquake','bi','extra_expense','parametric_quake'],
 'utility_failure':['utility','bi','non_damage_bi','parametric_outage'],
 'supplier_disruption':['cbi','bi','non_damage_bi'],
 'civil_authority':['civil_authority','bi','extra_expense'],
 'geopolitical':['political','non_damage_bi','cbi'],
 'cyber':['non_damage_bi'],
 'operational':['equipment','bi','extra_expense'],
 'other':[],
}
FIELDS=('scenario_name','interruption_cause','affected_dependency',
        'scenario_description','assumption_basis','reference_url',
        'gross_outage_days','margin_at_risk_daily_usd',
        'outage_mitigation_fraction','recovery_ramp_days',
        'recovery_average_capacity','extra_expense_usd',
        'stock_spoilage_usd','property_repair_usd')


def initialize_interruption(conn):
    conn.executescript(SCHEMA)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value,limit,required=False):
    if not isinstance(value,str):raise ValueError('A scenario text field must be supplied')
    value=' '.join(value.split())
    if len(value)>limit or (required and not value):
        raise ValueError('Missing or overlong scenario text field')
    return value


def _number(value,maximum,required=False):
    if value is None or value=='':
        if required:raise ValueError('Required downtime or financial assumption is absent')
        return None
    if isinstance(value,bool):raise ValueError('Numeric assumption required')
    try:number=float(value)
    except (TypeError,ValueError):raise ValueError('Numeric assumption required') from None
    if not math.isfinite(number) or number<0 or number>maximum:
        raise ValueError('Financial/downtime assumption outside permitted range')
    return number


def _actor(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9._-]{3,64}',value) or value in (
       'local-development','service-account'):
        raise ValueError('Individually authenticated researcher required')
    return value


def _details(data):
    if not isinstance(data,dict):raise ValueError('Scenario assumptions must be an object')
    cause=_text(data.get('interruption_cause'),50,True)
    dependency=_text(data.get('affected_dependency'),50,True)
    if cause not in CAUSES:raise ValueError('Unrecognized interruption cause')
    if dependency not in DEPENDENCIES:raise ValueError('Unrecognized operational dependency')
    from urllib.parse import urlsplit
    url=_text(data.get('reference_url',''),1200)
    if url:
        try:u=urlsplit(url)
        except ValueError:raise ValueError('Malformed reference URL') from None
        if u.scheme!='https' or not u.hostname or u.username or u.password:
            raise ValueError('Reference must be a valid HTTPS URL')
    return {
        'scenario_name':_text(data.get('scenario_name'),200,True),
        'interruption_cause':cause,'affected_dependency':dependency,
        'scenario_description':_text(data.get('scenario_description',''),2000),
        'assumption_basis':_text(data.get('assumption_basis',''),2000),
        'reference_url':url,
        'gross_outage_days':_number(data.get('gross_outage_days'),3650,True),
        'margin_at_risk_daily_usd':_number(data.get('margin_at_risk_daily_usd'),1e12,True),
        'outage_mitigation_fraction':_number(data.get('outage_mitigation_fraction',0),1,True),
        'recovery_ramp_days':_number(data.get('recovery_ramp_days',0),3650,True),
        'recovery_average_capacity':_number(data.get('recovery_average_capacity',1),1,True),
        'extra_expense_usd':_number(data.get('extra_expense_usd'),1e12),
        'stock_spoilage_usd':_number(data.get('stock_spoilage_usd'),1e12),
        'property_repair_usd':_number(data.get('property_repair_usd'),1e12)
    }


def _exists(conn,query,params,reason):
    row=conn.execute(query,params).fetchone()
    if not row:raise ValueError(reason)
    return row


def save_scenario(conn,facility_id,details,actor,scenario_id=''):
    actor=_actor(actor)
    _exists(conn,'SELECT id FROM facilities WHERE id=?',(facility_id,),'Unknown facility')
    if scenario_id:
        old=_exists(conn,'SELECT * FROM interruption_scenarios WHERE id=? AND facility_id=?',
                 (scenario_id,facility_id),'Unknown facility scenario')
    else:
        old=None
        count=conn.execute('SELECT COUNT(*) FROM interruption_scenarios WHERE facility_id=?',
                          (facility_id,)).fetchone()[0]
        if count>=100:raise ValueError('Private facility scenario limit reached')
    parsed=_details(details)
    ident=scenario_id if old else uuid.uuid4().hex
    revised=(old['revision']+1) if old else 1
    now=_now()
    with conn:
        conn.execute("""INSERT INTO interruption_scenarios (
           id,facility_id,scenario_name,interruption_cause,affected_dependency,
           scenario_description,assumption_basis,reference_url,
           gross_outage_days,margin_at_risk_daily_usd,outage_mitigation_fraction,
           recovery_ramp_days,recovery_average_capacity,
           extra_expense_usd,stock_spoilage_usd,property_repair_usd,
           revision,entered_by,created_at,changed_by,changed_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             scenario_name=excluded.scenario_name,
             interruption_cause=excluded.interruption_cause,
             affected_dependency=excluded.affected_dependency,
             scenario_description=excluded.scenario_description,
             assumption_basis=excluded.assumption_basis,
             reference_url=excluded.reference_url,
             gross_outage_days=excluded.gross_outage_days,
             margin_at_risk_daily_usd=excluded.margin_at_risk_daily_usd,
             outage_mitigation_fraction=excluded.outage_mitigation_fraction,
             recovery_ramp_days=excluded.recovery_ramp_days,
             recovery_average_capacity=excluded.recovery_average_capacity,
             extra_expense_usd=excluded.extra_expense_usd,
             stock_spoilage_usd=excluded.stock_spoilage_usd,
             property_repair_usd=excluded.property_repair_usd,
             revision=excluded.revision,changed_by=excluded.changed_by,
             changed_at=excluded.changed_at""",
           (ident,facility_id,*(parsed[k] for k in FIELDS),
            revised,old['entered_by'] if old else actor,
            old['created_at'] if old else now,actor,now))
        audit(conn,'interruption_assumption_'+('changed' if old else 'created'),
              facility_id,actor,{'scenario_id':ident,'revision':revised,
              'status':'analyst_assumptions_only'})
    return {'scenario_id':ident,'revision':revised,
            'status':'illustrative_assumptions_unverified',
            'confirmed_policy_recovery':None}


def calculate_components(fields):
    """No cross-category sum: amounts may overlap with property and BI wording."""
    outage_days=fields['gross_outage_days']
    daily=fields['margin_at_risk_daily_usd']
    mitigated=fields['outage_mitigation_fraction']
    ramp_days=fields['recovery_ramp_days']
    remaining_capacity=fields['recovery_average_capacity']
    unavailable_days=outage_days*(1-mitigated)
    ramp_equivalent_days=ramp_days*(1-remaining_capacity)
    margin=round(daily*(unavailable_days+ramp_equivalent_days),2)
    return {
      'status':'illustrative_assumptions_unverified',
      'operating_outage_days':outage_days,
      'outage_mitigation_fraction':mitigated,
      'recovery_ramp_days':ramp_days,
      'recovery_average_capacity':remaining_capacity,
      'equivalent_lost_operating_days':round(unavailable_days+ramp_equivalent_days,5),
      'illustrative_lost_contribution_margin_usd':margin,
      'additional_expense_components_usd':{
        'extra_expense':fields.get('extra_expense_usd'),
        'spoilage_or_inventory':fields.get('stock_spoilage_usd'),
        'property_repair':fields.get('property_repair_usd')},
      'gross_combined_claim_usd':None,
      'verified_insured_recovery_usd':None,
      'verified_coverage_status':'unknown',
      'coverage_topics_to_review':COVERAGE_LOOKUP.get(fields['interruption_cause'],[]),
      'contract_conditions_to_review':[
         'Insured location schedule and insurable interest',
         'Actual covered peril and required property damage, if applicable',
         'Service/supplier attachment conditions and waiting periods',
         'Deductibles, indemnity periods, policy limits and exclusions',
         'Documented actual loss, mitigation costs and loss adjustment',
         'Parametric index agreement, trigger, payout ladder and basis risk if relevant'],
      'limitations':[
         'This is arithmetic on analyst-supplied assumptions, not verified site loss',
         'Contribution margin at risk is a business-specific input, not gross revenue',
         'Outage and restart assumptions must be checked for double counting',
         'Repair, spoilage and extra expense components may overlap; no combined claim is asserted',
         'No contract coverage, probability, catastrophe loss or parametric payout is inferred']}


def facility_scenarios(conn,facility_id):
    _exists(conn,'SELECT id FROM facilities WHERE id=?',(facility_id,),'Unknown facility')
    rows=[]
    for r in conn.execute("""SELECT * FROM interruption_scenarios
           WHERE facility_id=? ORDER BY changed_at DESC,id""",(facility_id,)):
        s=dict(r)
        s['illustration']=calculate_components(s)
        rows.append(s)
    return {'facility_id':facility_id,'scenarios':rows,'count':len(rows),
        'risk_probability':None,'total_insured_recovery_usd':None,
        'warning':'All values are unverified private assumptions, not claims or insured payouts'}

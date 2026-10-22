"""Insurance coverage applicability taxonomy; no implied policy attachment.

This is a public reference framework, not a premium model or verified coverage.
Coverage status is UNKNOWN until actual policy evidence is separately reviewed.
"""
from __future__ import annotations

COVERAGES = [
 ('property','Commercial property','Property damage',
  'Insured physical loss from a covered cause at insured property',
  'Direct physical loss and applicable peril wording; exclusions, deductibles and sublimits'),
 ('flood','Flood / excess flood','Natural catastrophe',
  'Covered flood at insured location','Flood definition, flood zone, elevation, waiting terms and flood sublimits'),
 ('earthquake','Earthquake / DIC','Natural catastrophe',
  'Covered earthquake-related property damage','Earthquake exclusions, DIC wording and percentage deductible'),
 ('windstorm','Windstorm / named storm','Natural catastrophe',
  'Covered wind damage','Named-storm definition, deductibles, hurricane sublimits'),
 ('wildfire','Wildfire','Natural catastrophe',
  'Covered fire / smoke damage','Wildfire exclusions, smoke/ash wording and fire suppression'),
 ('bi','Business interruption','Operational interruption',
  'Covered interruption attributable to insured property damage',
  'Actual loss sustained, indemnity period, time deductible and physical-damage condition'),
 ('extra_expense','Extra expense','Operational interruption',
  'Covered extra costs incurred to resume operations','Expense limits, period of restoration and covered cause'),
 ('utility','Utility service interruption','Operational interruption',
  'Qualifying off-premises utility damage or specially endorsed outage',
  'Named utility services, off-premises damage requirement, service distance, overhead exclusions, waiting period'),
 ('cbi','Contingent business interruption','Operational interruption',
  'Qualifying covered damage at identified supplier or customer',
  'Scheduled or unnamed dependency, insured peril, tier, territory and sublimit'),
 ('civil_authority','Civil authority / ingress-egress','Operational interruption',
  'Covered civil access restriction or inability to enter',
  'Covered damage or non-damage endorsement, distance radius and maximum period'),
 ('non_damage_bi','Specialty non-damage business interruption','Operational interruption',
  'Expressly specified event without insured property damage',
  'Named trigger, exclusions and loss-validation rules; not part of ordinary BI'),
 ('equipment','Equipment breakdown / spoilage','Equipment and inventory',
  'Accidental breakdown of insured covered equipment',
  'Temperature-sensitive stock, backup power and service interruption wording'),
 ('parametric_wind','Parametric wind / hurricane','Parametric',
  'Objective contract-index wind speed or modeled hurricane intensity',
  'Measurement authority, location grid, threshold, payout ladder and basis risk'),
 ('parametric_flood','Parametric flood','Parametric',
  'Verified specified water height, rainfall index or modeled inundation',
  'Sensor/model, geospatial reference, trigger, exclusions and basis risk'),
 ('parametric_quake','Parametric earthquake','Parametric',
  'Verified PGA, intensity or event-index threshold',
  'USGS/model source, epicentral proximity, shaking basis and payout schedule'),
 ('parametric_outage','Parametric utility outage','Parametric',
  'Independently verified qualifying grid/service downtime',
  'Serving utility, trigger duration, measurement and exception rules'),
 ('parametric_wildfire','Parametric wildfire','Parametric',
  'Verified fire footprint, modeled intensity or contract proximity index',
  'Independent data authority, polygon reference and basis risk'),
 ('political','Political violence / political risk','Specialty',
  'Specified violence, expropriation or contractually defined political event',
  'Geographical exclusions, war/terror definitions and waiting periods'),
 ('environmental','Environmental impairment liability','Liability',
  'Contract-defined pollution or contamination event',
  'Sudden/gradual pollution, cleanup, offsite liability and retroactive dates')
]

def taxonomy():
    return [{'id':i,'name':name,'category':cat,'potential_trigger':trigger,
             'review_requirements':check,'verified_coverage':'unknown',
             'applicability':'requires_facility_and_contract_review'}
            for i,name,cat,trigger,check in COVERAGES]

def facility_screening(*,hazards=None,utility_dependency=None,has_policy_documents=False):
    hazards=hazards or []
    hazard_set={str(x).casefold() for x in hazards}
    suggestions=[]
    match={'flood':'flood','earthquake':'earthquake','wind':'windstorm',
           'hurricane':'windstorm','wildfire':'wildfire'}
    for h,k in match.items():
        if h in hazard_set and k not in suggestions:suggestions.append(k)
    if utility_dependency is True:
        suggestions.extend(['utility','parametric_outage'])
    return {'potentially_relevant_coverages':suggestions,
            'verified_coverages':[],
            'coverage_verification':'unassessed' if not has_policy_documents else 'requires_manual_policy_review',
            'method':'Hazard and dependency screening only; no contract coverage determined',
            'disclaimer':'No insured coverage, payout, insurable interest or risk score is asserted'}

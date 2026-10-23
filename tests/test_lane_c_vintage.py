"""Official CSB release comparisons must not assume Number is a permanent key."""
from scripts.probe_lane_c_current_vintages import compare_quarters

def test_csb_quarter_key_reuse_requires_matching_event_fields():
    q2={
        "1":("2026-01-01","company one","city","texas"),
        "2":("2026-01-02","company two","city","texas"),
        "4":("2026-01-04","company four","city","texas"),
    }
    q3={
        "1":("2026-01-01","company one","city","texas"),
        "2":("2026-03-02","company two","city","texas"),
        "3":("2026-03-03","company three","city","texas"),
    }
    a=compare_quarters(q2,q3)
    assert a["old_release_rows"]==3
    assert a["new_release_rows"]==3
    assert a["reused_number_count"]==2
    assert a["changed_event_attributes_under_same_number"]==1
    assert a["numbers_absent_in_new_release"]==1
    assert a["new_number_values"]==1
    assert a["safe_cross_vintage_id_assumption"] is False

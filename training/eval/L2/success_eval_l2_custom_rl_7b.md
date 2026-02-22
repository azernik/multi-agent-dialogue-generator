# Scenario-wise conversation success (L2 eval)

Prediction files discovered under: `/home/achakr24/RLVR/multi-agent-dialogue-generator/training`

**Scoring:** Turns evaluated in order; stop on first wrong turn. Score = correct turns so far / turns attempted. First turn wrong → 0% for that conversation. Tool names: exact or fuzzy (case-insensitive, small edit distance).

---

## Overall by model

| Model | Conversations | Overall success (%) |
| :---- | -------------: | ------------------: |
| rl_7b | 83 | 35.30 |

---

## Per-scenario success by model

| Scenario | rl_7b |
| :------- | --------: |
| ba_014 | 0.00 |
| ba_rc_012 | 66.67 |
| ba_rc_014 | 0.00 |
| ca_oe_005 | 50.00 |
| ca_rm_001 | 0.00 |
| ca_rm_003 | 61.11 |
| ca_rm_004 | 66.67 |
| ca_rm_006 | 50.00 |
| ca_rm_007 | 0.00 |
| ca_rm_008 | 66.67 |
| ca_rm_009 | 66.67 |
| ca_rm_013 | 0.00 |
| ca_sm_001 | 58.33 |
| hs_rf_001 | 0.00 |
| hs_rf_002 | 50.00 |
| hs_rf_005 | 50.00 |
| hs_rf_008 | 50.00 |
| hs_rf_011 | 50.00 |
| hs_rf_017 | 50.00 |
| hs_rs_001 | 25.00 |
| hs_rs_002 | 58.33 |
| hs_rs_003 | 50.00 |
| hs_rs_005 | 0.00 |
| hs_rs_010 | 0.00 |
| hs_rs_011 | 0.00 |
| hs_rs_013 | 0.00 |
| hs_ss_002 | 0.00 |
| hs_ss_003 | 50.00 |
| hs_ss_004 | 50.00 |
| hs_ss_005 | 75.00 |
| hs_ss_015 | 50.00 |
| os_co_001 | 44.44 |
| os_co_002 | 44.44 |
| os_co_003 | 16.67 |
| os_co_004 | 0.00 |
| os_co_006 | 65.56 |
| os_co_009 | 0.00 |
| os_co_010 | 44.44 |
| os_co_011 | 0.00 |
| os_co_012 | 66.67 |
| os_co_013 | 50.00 |
| os_co_014 | 66.67 |
| os_ro_002 | 0.00 |
| os_ro_005 | 63.89 |
| os_ro_006 | 0.00 |
| os_ro_010 | 66.67 |
| os_ro_011 | 50.00 |
| os_ro_012 | 66.67 |
| os_to_004 | 50.00 |
| rb_001 | 0.00 |
| rb_002 | 58.33 |
| rb_003 | 44.44 |
| rb_011 | 0.00 |
| tr_cfs_007 | 0.00 |
# Persistent Depth History GO-PD4 checkpoint

完了: 2026-07-29 07:49 JST  
承認: user `GO-PD4`

## 完了

- compose compatibility flag `PERSISTENT_DEPTH_HISTORY_ENABLED=false` added.
- backend container recreated with flag OFF.
- health recovered from startup UNKNOWN to GREEN.
- rollback image tag and temporary container rehearsal verified.
- PD3／PD4 isolated tests: **4 passed**.

## 未完了

- persistent writer enablement／schema／archive／retention
- production persistence soak

Next resume position: explicit `GO-PD5` for operational activation of persistent depth history, after user review of PD0–PD4 evidence.

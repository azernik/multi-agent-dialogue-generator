# Evaluation Report

Prediction files were read from: `training/models_apigen2`

## Summary

This report covers **13** model(s). **Conversation completeness** (well-formed outputs) averages **89.2%** across models. **Conversation success** (correct action type and, for tools, correct name and arguments) is highest for **custom_14b_cp17** at **59.69%**. Below you find per-model completeness and success, domain-wise analysis where metadata is available, and possible vs impossible scenario breakdowns. When plots are enabled, see also: `completeness_and_success.png`, `success_leaderboard.png`, `completeness_vs_success_scatter.png`, `metric_funnel.png`, and `success_by_domain.png` (if multiple domains).

---

## 1. Conversation completeness

**Completeness** is the share of turns where the model produced a valid, well-formed action block (correct `<think>`/`<plan>`/`<action>` structure and parseable output).

| Model | Samples | Completeness (%) |
|-------|--------|------------------|
| apigen_14b_epoch1 | 521 | 90.21 |
| apigen_14b_epoch3 | 521 | 89.64 |
| apigen_14b_epoch5 | 521 | 90.21 |
| apigen_32b_epoch1 | 521 | 82.34 |
| apigen_32b_epoch3 | 521 | 82.92 |
| apigen_32b_epoch5 | 521 | 82.92 |
| apigen_7b_cp114 | 521 | 91.36 |
| apigen_7b_cp185 | 521 | 91.17 |
| apigen_7b_cp38 | 521 | 89.64 |
| custom_14b_cp17 | 521 | 93.09 |
| custom_14b_cp51 | 521 | 93.09 |
| custom_14b_cp85 | 521 | 91.55 |
| custom_7b_cp33 | 521 | 90.98 |

---

## 2. Conversation success

**Success** means the model output was complete *and* matched the gold response: same action type (say vs tool), and for tool actions, correct tool name and arguments.

| Model | Samples | Success (%) |
|-------|--------|-------------|
| apigen_14b_epoch1 | 521 | 52.59 |
| apigen_14b_epoch3 | 521 | 51.63 |
| apigen_14b_epoch5 | 521 | 53.55 |
| apigen_32b_epoch1 | 521 | 50.29 |
| apigen_32b_epoch3 | 521 | 50.86 |
| apigen_32b_epoch5 | 521 | 51.06 |
| apigen_7b_cp114 | 521 | 51.82 |
| apigen_7b_cp185 | 521 | 52.4 |
| apigen_7b_cp38 | 521 | 51.25 |
| custom_14b_cp17 | 521 | 59.69 |
| custom_14b_cp51 | 521 | 55.85 |
| custom_14b_cp85 | 521 | 54.13 |
| custom_7b_cp33 | 521 | 48.18 |

---

## 3. Domain-wise conversation analysis

### apigen_14b_epoch1

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 100.0 | 53.85 |
| calendar_assistant | 70 | 97.14 | 45.71 |
| home_services | 111 | 90.99 | 50.45 |
| online_shopping | 231 | 86.58 | 51.08 |
| restaurant_booking | 92 | 91.3 | 65.22 |
| travel | 4 | 100.0 | 25.0 |

### apigen_14b_epoch3

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 100.0 | 46.15 |
| calendar_assistant | 70 | 94.29 | 47.14 |
| home_services | 111 | 90.09 | 45.05 |
| online_shopping | 231 | 87.88 | 51.52 |
| restaurant_booking | 92 | 89.13 | 63.04 |
| travel | 4 | 75.0 | 75.0 |

### apigen_14b_epoch5

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 100.0 | 46.15 |
| calendar_assistant | 70 | 98.57 | 50.0 |
| home_services | 111 | 89.19 | 48.65 |
| online_shopping | 231 | 87.01 | 53.25 |
| restaurant_booking | 92 | 91.3 | 63.04 |
| travel | 4 | 100.0 | 75.0 |

### apigen_32b_epoch1

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 76.92 | 46.15 |
| calendar_assistant | 70 | 81.43 | 40.0 |
| home_services | 111 | 80.18 | 40.54 |
| online_shopping | 231 | 81.39 | 51.08 |
| restaurant_booking | 92 | 89.13 | 67.39 |
| travel | 4 | 75.0 | 75.0 |

### apigen_32b_epoch3

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 76.92 | 46.15 |
| calendar_assistant | 70 | 82.86 | 41.43 |
| home_services | 111 | 81.98 | 44.14 |
| online_shopping | 231 | 81.39 | 51.08 |
| restaurant_booking | 92 | 89.13 | 66.3 |
| travel | 4 | 75.0 | 50.0 |

### apigen_32b_epoch5

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 76.92 | 46.15 |
| calendar_assistant | 70 | 81.43 | 40.0 |
| home_services | 111 | 81.98 | 43.24 |
| online_shopping | 231 | 81.39 | 51.52 |
| restaurant_booking | 92 | 90.22 | 67.39 |
| travel | 4 | 75.0 | 75.0 |

### apigen_7b_cp114

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 92.31 | 46.15 |
| calendar_assistant | 70 | 97.14 | 48.57 |
| home_services | 111 | 92.79 | 54.05 |
| online_shopping | 231 | 90.48 | 50.22 |
| restaurant_booking | 92 | 88.04 | 57.61 |
| travel | 4 | 75.0 | 25.0 |

### apigen_7b_cp185

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 84.62 | 46.15 |
| calendar_assistant | 70 | 95.71 | 47.14 |
| home_services | 111 | 92.79 | 55.86 |
| online_shopping | 231 | 90.04 | 50.65 |
| restaurant_booking | 92 | 89.13 | 58.7 |
| travel | 4 | 100.0 | 25.0 |

### apigen_7b_cp38

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 84.62 | 46.15 |
| calendar_assistant | 70 | 97.14 | 48.57 |
| home_services | 111 | 90.09 | 50.45 |
| online_shopping | 231 | 89.18 | 50.65 |
| restaurant_booking | 92 | 84.78 | 55.43 |
| travel | 4 | 100.0 | 75.0 |

### custom_14b_cp17

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 100.0 | 61.54 |
| calendar_assistant | 70 | 98.57 | 52.86 |
| home_services | 111 | 93.69 | 54.95 |
| online_shopping | 231 | 90.48 | 59.31 |
| restaurant_booking | 92 | 93.48 | 72.83 |
| travel | 4 | 100.0 | 25.0 |

### custom_14b_cp51

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 100.0 | 69.23 |
| calendar_assistant | 70 | 100.0 | 51.43 |
| home_services | 111 | 92.79 | 53.15 |
| online_shopping | 231 | 90.48 | 51.95 |
| restaurant_booking | 92 | 93.48 | 70.65 |
| travel | 4 | 100.0 | 50.0 |

### custom_14b_cp85

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 100.0 | 46.15 |
| calendar_assistant | 70 | 98.57 | 52.86 |
| home_services | 111 | 92.79 | 52.25 |
| online_shopping | 231 | 87.45 | 48.05 |
| restaurant_booking | 92 | 93.48 | 72.83 |
| travel | 4 | 100.0 | 75.0 |

### custom_7b_cp33

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| banking | 13 | 92.31 | 69.23 |
| calendar_assistant | 70 | 97.14 | 55.71 |
| home_services | 111 | 92.79 | 48.65 |
| online_shopping | 231 | 89.18 | 39.83 |
| restaurant_booking | 92 | 88.04 | 58.7 |
| travel | 4 | 100.0 | 75.0 |

---

## 4. Possible vs impossible scenarios

### apigen_14b_epoch1

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 89.8 | 53.06 |
| impossible | 31 | 96.77 | 45.16 |

### apigen_14b_epoch3

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 89.39 | 52.65 |
| impossible | 31 | 93.55 | 35.48 |

### apigen_14b_epoch5

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 89.8 | 53.88 |
| impossible | 31 | 96.77 | 48.39 |

### apigen_32b_epoch1

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 82.24 | 51.43 |
| impossible | 31 | 83.87 | 32.26 |

### apigen_32b_epoch3

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 82.86 | 52.04 |
| impossible | 31 | 83.87 | 32.26 |

### apigen_32b_epoch5

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 82.86 | 52.04 |
| impossible | 31 | 83.87 | 35.48 |

### apigen_7b_cp114

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 91.22 | 52.45 |
| impossible | 31 | 93.55 | 41.94 |

### apigen_7b_cp185

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 90.82 | 53.06 |
| impossible | 31 | 96.77 | 41.94 |

### apigen_7b_cp38

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 89.18 | 51.43 |
| impossible | 31 | 96.77 | 48.39 |

### custom_14b_cp17

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 92.86 | 60.41 |
| impossible | 31 | 96.77 | 48.39 |

### custom_14b_cp51

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 92.86 | 55.92 |
| impossible | 31 | 96.77 | 54.84 |

### custom_14b_cp85

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 91.43 | 54.08 |
| impossible | 31 | 93.55 | 54.84 |

### custom_7b_cp33

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 490 | 90.61 | 47.55 |
| impossible | 31 | 96.77 | 58.06 |


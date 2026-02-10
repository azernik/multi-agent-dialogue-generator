# Evaluation Report

Prediction files were read from: `training/models`

## Summary

This report covers **9** model(s). **Conversation completeness** (well-formed outputs) averages **88.8%** across models. **Conversation success** (correct action type and, for tools, correct name and arguments) is highest for **14b_epoch1** at **50.35%**. Below you find per-model completeness and success, domain-wise analysis where metadata is available, and possible vs impossible scenario breakdowns. When plots are enabled, see also: `completeness_and_success.png`, `success_leaderboard.png`, `completeness_vs_success_scatter.png`, `metric_funnel.png`, and `success_by_domain.png` (if multiple domains).

---

## 1. Conversation completeness

**Completeness** is the share of turns where the model produced a valid, well-formed action block (correct `<think>`/`<plan>`/`<action>` structure and parseable output).

| Model | Samples | Completeness (%) |
|-------|--------|------------------|
| 14b_epoch1 | 143 | 92.31 |
| 14b_epoch3 | 143 | 91.61 |
| 14b_epoch5 | 143 | 91.61 |
| 32b_epoch1 | 143 | 82.52 |
| 32b_epoch3 | 143 | 82.52 |
| 32b_epoch5 | 143 | 83.22 |
| 7b_checkpoint114 | 143 | 91.61 |
| 7b_checkpoint185 | 143 | 92.31 |
| 7b_checkpoint38 | 143 | 91.61 |

---

## 2. Conversation success

**Success** means the model output was complete *and* matched the gold response: same action type (say vs tool), and for tool actions, correct tool name and arguments.

| Model | Samples | Success (%) |
|-------|--------|-------------|
| 14b_epoch1 | 143 | 50.35 |
| 14b_epoch3 | 143 | 46.85 |
| 14b_epoch5 | 143 | 49.65 |
| 32b_epoch1 | 143 | 41.26 |
| 32b_epoch3 | 143 | 41.96 |
| 32b_epoch5 | 143 | 41.26 |
| 7b_checkpoint114 | 143 | 46.85 |
| 7b_checkpoint185 | 143 | 47.55 |
| 7b_checkpoint38 | 143 | 47.55 |

---

## 3. Domain-wise conversation analysis

### 14b_epoch1

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| calendar_assistant | 24 | 95.83 | 58.33 |
| home_services | 53 | 92.45 | 43.4 |
| online_shopping | 37 | 91.89 | 51.35 |
| restaurant_booking | 25 | 88.0 | 60.0 |
| travel | 4 | 100.0 | 25.0 |

### 14b_epoch3

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| calendar_assistant | 24 | 95.83 | 58.33 |
| home_services | 53 | 96.23 | 41.51 |
| online_shopping | 37 | 89.19 | 37.84 |
| restaurant_booking | 25 | 84.0 | 56.0 |
| travel | 4 | 75.0 | 75.0 |

### 14b_epoch5

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| calendar_assistant | 24 | 100.0 | 58.33 |
| home_services | 53 | 92.45 | 43.4 |
| online_shopping | 37 | 86.49 | 45.95 |
| restaurant_booking | 25 | 88.0 | 56.0 |
| travel | 4 | 100.0 | 75.0 |

### 32b_epoch1

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| calendar_assistant | 24 | 79.17 | 33.33 |
| home_services | 53 | 83.02 | 33.96 |
| online_shopping | 37 | 83.78 | 37.84 |
| restaurant_booking | 25 | 84.0 | 64.0 |
| travel | 4 | 75.0 | 75.0 |

### 32b_epoch3

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| calendar_assistant | 24 | 79.17 | 37.5 |
| home_services | 53 | 83.02 | 35.85 |
| online_shopping | 37 | 83.78 | 40.54 |
| restaurant_booking | 25 | 84.0 | 60.0 |
| travel | 4 | 75.0 | 50.0 |

### 32b_epoch5

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| calendar_assistant | 24 | 79.17 | 33.33 |
| home_services | 53 | 83.02 | 32.08 |
| online_shopping | 37 | 83.78 | 40.54 |
| restaurant_booking | 25 | 88.0 | 64.0 |
| travel | 4 | 75.0 | 75.0 |

### 7b_checkpoint114

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| calendar_assistant | 24 | 91.67 | 41.67 |
| home_services | 53 | 94.34 | 47.17 |
| online_shopping | 37 | 94.59 | 48.65 |
| restaurant_booking | 25 | 84.0 | 52.0 |
| travel | 4 | 75.0 | 25.0 |

### 7b_checkpoint185

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| calendar_assistant | 24 | 91.67 | 45.83 |
| home_services | 53 | 94.34 | 47.17 |
| online_shopping | 37 | 94.59 | 48.65 |
| restaurant_booking | 25 | 84.0 | 52.0 |
| travel | 4 | 100.0 | 25.0 |

### 7b_checkpoint38

| Domain | Count | Completeness (%) | Success (%) |
|--------|-------|------------------|-------------|
| calendar_assistant | 24 | 100.0 | 50.0 |
| home_services | 53 | 92.45 | 45.28 |
| online_shopping | 37 | 91.89 | 48.65 |
| restaurant_booking | 25 | 80.0 | 44.0 |
| travel | 4 | 100.0 | 75.0 |

---

## 4. Possible vs impossible scenarios

### 14b_epoch1

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 112 | 91.07 | 51.79 |
| impossible | 31 | 96.77 | 45.16 |

### 14b_epoch3

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 112 | 91.07 | 50.0 |
| impossible | 31 | 93.55 | 35.48 |

### 14b_epoch5

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 112 | 90.18 | 50.0 |
| impossible | 31 | 96.77 | 48.39 |

### 32b_epoch1

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 112 | 82.14 | 43.75 |
| impossible | 31 | 83.87 | 32.26 |

### 32b_epoch3

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 112 | 82.14 | 44.64 |
| impossible | 31 | 83.87 | 32.26 |

### 32b_epoch5

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 112 | 83.04 | 42.86 |
| impossible | 31 | 83.87 | 35.48 |

### 7b_checkpoint114

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 112 | 91.07 | 48.21 |
| impossible | 31 | 93.55 | 41.94 |

### 7b_checkpoint185

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 112 | 91.07 | 49.11 |
| impossible | 31 | 96.77 | 41.94 |

### 7b_checkpoint38

| Type | Count | Completeness (%) | Success (%) |
|------|-------|------------------|-------------|
| possible | 112 | 90.18 | 47.32 |
| impossible | 31 | 96.77 | 48.39 |


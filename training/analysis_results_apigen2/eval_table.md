# End-to-End Evaluation Results (Local Test Set)

**Metrics:** Compl = Completeness, Tool name = Tool name match, Tool args = Tool args match, Success = Full success (syntax + type + name + args). Possible / Impossible refer to scenario difficulty. Bold = best in column.

## Main results (overall, possible, impossible)

| Finetuning   | Model              | Compl | Tool name | Tool args | Success | Poss. Compl | Poss. Succ | Imposs. Compl | Imposs. Succ |
| :----------- | :----------------- | ----: | -------: | -------: | ------: | ----------: | ---------: | ------------: | -----------: |
| APIGen      | apigen_14b_epoch1 | 0.90 | 0.68 | 0.39 | 0.53 | 0.90 | 0.53 | **0.97** | 0.45 |
| APIGen      | apigen_14b_epoch3 | 0.90 | 0.68 | 0.42 | 0.52 | 0.89 | 0.53 | 0.94 | 0.35 |
| APIGen      | apigen_14b_epoch5 | 0.90 | 0.71 | 0.43 | 0.54 | 0.90 | 0.54 | **0.97** | 0.48 |
| APIGen      | apigen_32b_epoch1 | 0.82 | 0.77 | 0.45 | 0.50 | 0.82 | 0.51 | 0.84 | 0.32 |
| APIGen      | apigen_32b_epoch3 | 0.83 | 0.77 | 0.46 | 0.51 | 0.83 | 0.52 | 0.84 | 0.32 |
| APIGen      | apigen_32b_epoch5 | 0.83 | **0.78** | 0.47 | 0.51 | 0.83 | 0.52 | 0.84 | 0.35 |
| APIGen      | apigen_7b_cp114 | 0.91 | 0.64 | 0.29 | 0.52 | 0.91 | 0.52 | 0.94 | 0.42 |
| APIGen      | apigen_7b_cp185 | 0.91 | 0.65 | 0.31 | 0.52 | 0.91 | 0.53 | **0.97** | 0.42 |
| APIGen      | apigen_7b_cp38 | 0.90 | 0.63 | 0.29 | 0.51 | 0.89 | 0.51 | **0.97** | 0.48 |
| Custom data | custom_14b_cp17 | **0.93** | 0.67 | 0.41 | 0.60 | **0.93** | 0.60 | **0.97** | 0.48 |
| Custom data | custom_14b_cp51 | **0.93** | 0.66 | 0.37 | 0.56 | **0.93** | 0.56 | **0.97** | 0.55 |
| Custom data | custom_14b_cp85 | 0.92 | 0.62 | 0.35 | 0.54 | 0.91 | 0.54 | 0.94 | 0.55 |
| Custom data | custom_7b_cp33 | 0.91 | 0.39 | 0.20 | 0.48 | 0.91 | 0.48 | **0.97** | 0.58 |
| RL          | rl_32b | 0.92 | **0.78** | **0.53** | **0.66** | 0.91 | **0.66** | **0.97** | **0.61** |
| RL          | rl_7b | 0.72 | 0.59 | 0.34 | 0.45 | 0.72 | 0.45 | 0.81 | 0.45 |

## By domain (success)

Per-domain success rate. Use to compare **seen** vs **unseen** domains depending on your training setup.

| Finetuning   | Model              | banking | calendar | home_services | online_shop | restaurant | travel |
| :----------- | :----------------- | -----: | -----: | -----: | -----: | -----: | -----: |
| APIGen      | apigen_14b_epoch1 | 0.54 | 0.46 | 0.50 | 0.51 | 0.65 | 0.25 |
| APIGen      | apigen_14b_epoch3 | 0.46 | 0.47 | 0.45 | 0.52 | 0.63 | 0.75 |
| APIGen      | apigen_14b_epoch5 | 0.46 | 0.50 | 0.49 | 0.53 | 0.63 | 0.75 |
| APIGen      | apigen_32b_epoch1 | 0.46 | 0.40 | 0.41 | 0.51 | 0.67 | 0.75 |
| APIGen      | apigen_32b_epoch3 | 0.46 | 0.41 | 0.44 | 0.51 | 0.66 | 0.50 |
| APIGen      | apigen_32b_epoch5 | 0.46 | 0.40 | 0.43 | 0.52 | 0.67 | 0.75 |
| APIGen      | apigen_7b_cp114 | 0.46 | 0.49 | 0.54 | 0.50 | 0.58 | 0.25 |
| APIGen      | apigen_7b_cp185 | 0.46 | 0.47 | 0.56 | 0.51 | 0.59 | 0.25 |
| APIGen      | apigen_7b_cp38 | 0.46 | 0.49 | 0.50 | 0.51 | 0.55 | 0.75 |
| Custom data | custom_14b_cp17 | 0.62 | 0.53 | 0.55 | 0.59 | 0.73 | 0.25 |
| Custom data | custom_14b_cp51 | 0.69 | 0.51 | 0.53 | 0.52 | 0.71 | 0.50 |
| Custom data | custom_14b_cp85 | 0.46 | 0.53 | 0.52 | 0.48 | 0.73 | 0.75 |
| Custom data | custom_7b_cp33 | 0.69 | 0.56 | 0.49 | 0.40 | 0.59 | 0.75 |
| RL          | rl_32b | 0.69 | 0.63 | 0.56 | 0.65 | 0.80 | 1.00 |
| RL          | rl_7b | 0.46 | 0.43 | 0.36 | 0.42 | 0.65 | 0.75 |
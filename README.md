# CI-Sense research

Research comparing flaky-test predictions from code (B0), code plus failure reports (B1), and code plus reports plus a project change description (B2_o1). The independent dashboard is maintained at https://github.com/Krishnakd24/CI-sense_dashboard.

## Directory structure

```text
CI-Sense-research/
|-- experiments/
|   |-- CI_SENSE_experiments.ipynb  # Main B0, B1, and B2_o1 notebook
|   |-- convert_b0.py              # B0 CSV-to-JSON conversion
|   |-- convert_b1.py              # Join code and ordered failure reports
|   |-- prepare_b2_o1.py           # Add project change descriptions
|   |-- b*_runner.py              # Standalone inference helpers
|   |-- b*_parallel.py            # Parallel execution helpers
|   |-- b*_evaluation.py          # Evaluation helpers
|   |-- retry_*_errors.py         # Retry unresolved predictions
|   |-- *.csv                     # Frozen inputs, labels, and project mappings
|   |-- *_data_v1.json            # Structured model inputs
|   |-- b0_few_shot.json           # B0 example provenance
|   |-- prompt_*.txt              # Exact prompts and templates
|   |-- requirements_b0.txt        # Standalone experiment dependencies
|   |-- diffs/                    # Project commit diffs
|   |-- b0_results/
|   |   |-- b0_flash_medium_v1/    # Earlier B0 run
|   |   `-- b0_flash_medium_v2/    # Completed B0 experiment
|   |-- b1_results/
|   |   |-- pilot_v1/
|   |   `-- b1_flash_medium_v1/    # Completed B1 experiment
|   `-- b2_o1_results/
|       |-- pilot_v1/
|       `-- b2_o1_flash_medium_v1/ # Completed B2_o1 experiment
|-- data_preparation/
|   |-- <project-name>/           # Original XML failure reports, by project
|   |-- extract_test_code.py
|   |-- extract_test_failure_details.ps1
|   |-- inspect_sample_diffs.ps1
|   |-- NOT_A_PROJECT_sample_commit_diffs/ # Historical diffs and summary
|   |-- *.csv                     # Source tables, extracted data, identity checks
|   `-- ...                       # Verification and historical publishing helpers
|-- archive/
|   |-- earlier-experiments/      # Earlier notebooks and operational utilities
|   `-- previous-repository-layout/ # Preserved original repository files
|-- references/
|   `-- berndt26-flaky.pdf
|-- .gitignore
|-- requirements.txt
`-- README.md
```

Wildcard entries group existing files for readability. Local-only handoff notes, caches, and Git metadata are omitted from this submission tree. Each result directory contains the files produced by that run; completed runs include prediction logs, manifests, metrics, and comparisons.

| Folder | Contents |
|---|---|
| experiments/ | Consolidated notebook, converters, runners, retry/evaluation helpers, frozen CSVs, structured JSON inputs, exact prompts, diffs, and saved results |
| data_preparation/ | Original project XML folders, historical tables, extracted code/reports, identity checks, project/commit mapping, and extraction utilities |
| archive/earlier-experiments/ | Earlier notebooks, pilots, authentication utility, and machine-specific retry launcher |
| archive/previous-repository-layout/ | Preserved copies of the former repository notebook, converters, and B1 template |
| references/ | Existing reference PDF, retained unchanged |

Experiment code, inputs, and result folders stay together to preserve existing relative paths. Canonical experiment inputs are in experiments; duplicate CSVs under data_preparation are preserved preparation outputs. No research scripts, datasets, prompts, notebooks, or results were regenerated during organization.

Local handoff notes, credentials, caches, and lock files are ignored. Earlier dataset Git checkouts are preserved outside both submission repositories in the local workspace's repository-archives folder.

## Review and run

```powershell
python -m pip install -r requirements.txt
cd experiments
jupyter notebook CI_SENSE_experiments.ipynb
```

Set the notebook working directory to experiments. Its six cells contain prediction and comparison for B0, B1, and B2_o1. Three comparison cells already have saved outputs; reading them makes no model calls. Rerunning comparisons reads the supplied logs.

Prediction requires a separately installed/authenticated Antigravity CLI (agy) and the configured model. Prediction cells make real calls, default to eight workers and three independent predictions per test, and may consume quota. Empty ID lists select all 300 tests. Calls use independent conversations, checkpointing, shared authentication pauses, and retries.

Completed B0/B1 results are v2/v1. Their prediction defaults use future v3/v2 names to protect completed results. Use new names for changed configurations. Manifests may reject resuming with changed code/configuration hashes. Do not run multiple schedulers on one result folder.

Generated JSON inputs are supplied. convert_b0.py, convert_b1.py, and prepare_b2_o1.py document transformations and refuse to overwrite outputs. B0 supports an alternative output filename. Do not delete supplied outputs merely to rerun preparation.

Archived scripts/notebooks retain their original contents and may require original working directories/import paths if reused. data_preparation/inspect_sample_diffs.ps1 writes to sample_commit_diffs; its historical output is named NOT_A_PROJECT_sample_commit_diffs. Publishing helpers retain historical local paths and are not submission entry points.

## Data and exact prompts

- b0_data.csv / b0_data_v1.json: 300 sampled test-code records.
- data_B1.csv / b1_data_v1.json: code and ordered failure reports. Thirty-nine tests have two matching entries; this does not establish separate executions.
- sample_300_labels.csv: evaluation labels; fleaky=1 means flaky. Labels are excluded from target prompts.
- id_project_mapping.csv, data_B3_v1.csv, data_B3_v2.csv, data_B3_v3.csv, and diffs/: project mapping, diffs, and successive descriptions.
- b2_o1_data_v1.json: B1 plus descriptions from data_B3_v3.csv. B3 filenames are preparation data, not a separate completed prediction experiment.
- prompt_b0.txt, prompt_b1.txt, prompt_b2_o1.txt, prompt_b2_o1_template.txt, and b0_few_shot.json: exact prompts/templates and example provenance. B0 uses four labeled examples; B1/B2_o1 use two.

The dashboard bundles a byte-identical copy of experiments/prompt_b2_o1.txt. At runtime the app replaces its probability-only output section with probability plus concise reasons. The research template is unchanged.

## Completed results

Each completed experiment has 900 accepted predictions: 300 tests times three runs. Majority-vote threshold is 0.5.

| Directory under experiments/ | Accuracy | TN | FP | FN | TP |
|---|---:|---:|---:|---:|---:|
| b0_results/b0_flash_medium_v2/ | 51.33% | 66 | 73 | 73 | 88 |
| b1_results/b1_flash_medium_v1/ | 84.33% | 134 | 5 | 42 | 119 |
| b2_o1_results/b2_o1_flash_medium_v1/ | 86.33% | 134 | 5 | 36 | 125 |

Inspect predictions.jsonl, manifests, metrics, variability, and comparison tables for execution/evaluation evidence. Pilot folders and B0 v1 are historical runs, not the primary completed results.

## Limitations

The sample deliberately contains 161 flaky and 139 non-flaky tests. Fixed examples are included among evaluated IDs. B0 uses more examples than B1/B2_o1, so B0-to-B1 does not isolate report context alone. Several tests share project context; held-out project/test evaluation is needed before generalization claims.

Project SHAs have not been established as failed CI build commits. First-parent diffs/descriptions are not proven causes of failures. One of 24 projects has a root commit, leaving 23 available diffs.

Completed B0/B1 runs used an earlier validator that rejected some internal finish steps and retried calls; rejected responses were not retained. Current code corrects that validator. Historical results were preserved, not rerun.

Probabilities are uncalibrated estimates; a single failure does not prove flakiness. Organization is not a fresh model run or live dashboard validation.

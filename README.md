# CI-Sense

Code for comparing flaky-test predictions from test code (B0), code plus failure reports (B1), and code plus reports plus a project change description (B2_o1). The notebook has six cells: prediction and comparison for each level. Prediction uses independent Antigravity CLI conversations, parallel workers, checkpointed outputs, and repeated attempts for unresolved predictions.

## Data and privacy

Raw datasets, label files, prediction logs, and prompts containing dataset examples are not included as separate files. The notebook contains saved comparison outputs, including metrics and selected prediction rows, for review by the professor. Obtain input and log files separately from their owner. `.gitignore` blocks common local data and result paths, but inspect staged files before every commit.

The B1 prompt in this repository is a template with placeholders; its examples are populated locally from the data. Each B0 prompt includes four examples. Each B1 and B2_o1 prompt includes two. Examples are also included in evaluations. Test names and project identifiers can still appear inside source code and stack traces. Predictions are uncalibrated model estimates.

## Setup

1. Install Python and dependencies: `python -m pip install -r requirements.txt`. Install and sign in to Antigravity CLI (`agy`) separately; ensure the selected model is available on your account.
2. Place the input files next to the notebook: `b0_data.csv`, `data_B1.csv`, `sample_300_labels.csv`, and the private `prompt_b0.txt` supplied separately. For B2_o1, also supply `b2_o1_data_v1.json` and `prompt_b2_o1.txt` privately. Keep these files local and untracked.
3. Run `python convert_b0.py` and `python convert_b1.py` to create `b0_data_v1.json` and `b1_data_v1.json`. The converters never overwrite existing outputs. B1 conversion joins the two CSVs by ID, preserves ordered report entries, drops explicit test identity fields, and omits unavailable (`NA` or empty) values.
4. Open `CI_SENSE_experiments.ipynb` with its working directory set to this repository. An empty ID list (`[]`) selects all tests; a list such as `["198", "200"]` selects only those IDs. Prediction cells make model calls and default to 8 workers and 3 runs; comparison cells use existing results only.

Each request uses a fresh conversation with tool restrictions and is rejected if tool use is reported. Quota or authentication issues stop dispatch and offer a shared login prompt after in-flight requests finish. Once signed in, resume; successful results are skipped. Recursive retries continue until selected predictions succeed or the user stops the cell. This can consume additional quota; persistent failures remain visible in local logs. Avoid running two schedulers for the same experiment at once.

The comparison cells are already executed and show the completed B0 v2, B1 v1, and B2_o1 v1 results in GitHub. Re-executing those comparison cells requires the private result logs in the matching result folders. The B0 and B1 prediction cells default to separate future experiment names (v3 and v2) so they cannot overwrite the completed logs. To start another experiment, use a new name in its prediction cell and point the corresponding comparison cell at that name.

The reported research sample is near balanced and need not represent deployment prevalence. Compare precision, recall, F1, confusion matrices, and run-to-run consistency as well as accuracy. Any threshold tuned on the same tests requires separate validation.

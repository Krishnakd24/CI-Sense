"""B0 prediction and evaluation helpers. Importing this module makes no calls."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

PRE_AUTH_FIX_SHA256 = "4ffaacc878b8617d58016be552f2874de6f7544e261cd5846fe98cb7741d06b7"


def interactive_login(cli, reason):
    """User handles OAuth in a real terminal, never in captured subprocess IO."""
    print(f"\n{reason}\nProgress is saved. No requests run while this prompt is waiting.")
    print("Choose login to open a visible Antigravity terminal. To switch accounts, "
          "enter /logout there, then sign in with the other account.")
    print("Paste any browser authorization code/link ONLY into that terminal's "
          "authorization prompt. After sign-in, exit the CLI with /exit.")
    while True:
        try:
            choice = input("Type login, ready (already signed in), or stop: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("Stopped. Sign in with agy in PowerShell, then rerun cell 1.")
            return False
        if choice == "stop":
            return False
        if choice == "ready":
            return True
        if choice == "login":
            if os.name == "nt":
                # Single-quoted PowerShell literal; never interpolate OAuth data.
                quoted_cli = "'" + str(cli).replace("'", "''") + "'"
                try:
                    subprocess.Popen(
                        ["powershell.exe", "-NoProfile", "-NoExit", "-Command", "& " + quoted_cli],
                        cwd=tempfile.gettempdir(), creationflags=subprocess.CREATE_NEW_CONSOLE,
                        stdin=None, stdout=None, stderr=None,
                    )
                except OSError as exc:
                    print(f"Cannot open terminal: {exc}. Open PowerShell and run agy manually.")
            else:
                print(f"Open a separate terminal and run: {cli}")
            print("Complete sign-in there, then return HERE and type ready. "
                  "If /logout closes the CLI, run agy again in that terminal.")
        else:
            print("Enter login, ready, or stop; do not paste authorization credentials here.")

SETTINGS = {
    "toolPermission": "strict", "useG1Credits": False,
    "disableSlashCommands": True, "allowNonWorkspaceAccess": False,
    "permissions": {"allow": [], "ask": [], "deny": [
        "read_url(*)", "execute_url(*)", "command(*)", "mcp(*)",
        "read_file(*)", "write_file(*)"]},
}
SCHEMA = {"type": "object", "properties": {"flaky_probability": {
    "type": "number", "minimum": 0, "maximum": 1}},
    "required": ["flaky_probability"], "additionalProperties": False}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_probability(value):
    if not isinstance(value, dict) or set(value) != {"flaky_probability"}:
        raise ValueError("Expected only flaky_probability")
    p = value["flaky_probability"]
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("Probability must be a finite number in [0,1]")
    return float(p)


def parse_response(stdout):
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    for event in events:
        step = event.get("step_update", {})
        tool = step.get("tool_info") or {}
        internal_finish = (step.get("step_type") == "tool" and
                           step.get("tool_name") == "finish" and
                           tool.get("name") == "finish" and
                           not step.get("subagent_info"))
        if (step.get("step_type") == "tool" or tool or step.get("subagent_info")) and not internal_finish:
            raise RuntimeError("Tool use detected; prediction rejected")
    results = [e["result"] for e in events if e.get("event") == "result"]
    if len(results) != 1:
        raise ValueError("Expected exactly one final CLI result")
    result = results[0]
    if result.get("status") != "SUCCESS":
        raise RuntimeError(str(result.get("error", result.get("status"))))
    value = result.get("structured_output")
    if value is None:
        value = json.loads(result["response"])
    return validate_probability(value), result


def classify_error(message):
    msg = message.lower()
    if any(s in msg for s in ("quota", "resource_exhausted", "429", "rate limit", "sign in", "sign-in", "logged in", "authentication", "credential", "credit", "authorization code", "unauthenticated")):
        return "blocked"
    if any(s in msg for s in ("timeout", "timed out", "503", "502", "temporarily", "connection reset")):
        return "transient"
    return "error"


def run_predictions(base, selected_ids=("198",), n_runs=1,
                    model="Gemini 3.8 Flash (Medium)", effort="medium",
                    experiment="b0_flash_medium_v1", timeout=300, cli=None,
                    login_before_run=True):
    base = Path(base).resolve()
    if not isinstance(n_runs, int) or isinstance(n_runs, bool) or n_runs < 1:
        raise ValueError("n_runs must be a positive integer")
    if Path(experiment).name != experiment or experiment in ("", ".", ".."):
        raise ValueError("experiment must be a simple folder name")
    data = json.loads((base / "b0_data_v1.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in data}
    if len(by_id) != len(data):
        raise ValueError("Duplicate input IDs")
    ids = list(by_id) if selected_ids is None else list(dict.fromkeys(map(str, selected_ids)))
    if not ids or set(ids) - set(by_id):
        raise ValueError("Select existing, nonempty IDs")
    prompt = (base / "prompt_b0.txt").read_text(encoding="utf-8")
    if prompt.count("{{TEST_CODE}}") != 1:
        raise ValueError("Prompt must contain exactly one target placeholder")
    cli = cli or shutil.which("agy") or str(Path.home() / "AppData/Local/agy/bin/agy.exe")
    if not Path(cli).is_file():
        raise FileNotFoundError("Antigravity CLI not found; configure CLI_PATH")
    config = {"model": model, "effort": effort, "prompt_sha256": digest(prompt),
              "data_sha256": digest(data), "settings": SETTINGS, "schema": SCHEMA,
              "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    folder = base / "b0_results" / experiment
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / "manifest.json"
    if manifest.exists():
        old = json.loads(manifest.read_text())
        if old != config:
            compatible_auth_fix = (old.get("runner_sha256") == PRE_AUTH_FIX_SHA256 and
                {k: v for k, v in old.items() if k != "runner_sha256"} ==
                {k: v for k, v in config.items() if k != "runner_sha256"})
            if not compatible_auth_fix:
                raise ValueError("Experiment configuration changed: use a new EXPERIMENT name")
            (folder / "manifest_before_auth_fix.json").write_text(json.dumps(old, indent=2), encoding="utf-8")
    manifest.write_text(json.dumps(config, indent=2), encoding="utf-8")
    (folder / "prompt_snapshot.txt").write_text(prompt, encoding="utf-8")
    log = folder / "predictions.jsonl"
    previous = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    done = {(r["run"], r["id"]) for r in previous if r["status"] == "success"}
    if all((run, ident) in done for run in range(1, n_runs + 1) for ident in ids):
        return folder
    if login_before_run and not interactive_login(cli, "Confirm interactive sign-in before starting predictions."):
        return folder
    auth_session = uuid.uuid4().hex  # Local audit marker, not an account identifier.
    # One NDJSON input message per fresh process avoids Windows command-length limits.
    for run in range(1, n_runs + 1):
        for ident in ids:
            if (run, ident) in done:
                continue
            target_prompt = prompt.replace("{{TEST_CODE}}", by_id[ident]["test_code"])
            attempt = 0
            transient_failures = 0
            while True:
                attempt += 1
                record = {"run": run, "id": ident, "model": model, "effort": effort,
                          "auth_session": auth_session,
                          "prompt_sha256": digest(target_prompt), "attempt": attempt,
                          "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                start = time.monotonic()
                try:
                    with tempfile.TemporaryDirectory(prefix="b0_inference_") as work:
                        command = [cli, "--input-format", "stream-json", "--output-format", "stream-json",
                                   "--model", model, "--disable-slash-commands",
                                   "--settings", json.dumps(SETTINGS), "--json-schema", json.dumps(SCHEMA),
                                   "--print-timeout", f"{timeout}s"]
                        if not model.endswith("(Medium)"):
                            command.extend(["--effort", effort])
                        elif effort != "medium":
                            raise ValueError("Medium model requires medium effort")
                        completed = subprocess.run(command, input=json.dumps({"event": "user", "message": {
                            "content": target_prompt}}) + "\n", capture_output=True, text=True,
                            encoding="utf-8", errors="replace", cwd=work, timeout=timeout + 30,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if completed.returncode:
                        if classify_error(completed.stderr + "\n" + completed.stdout) == "blocked":
                            raise RuntimeError("Authentication or account quota/credits require attention")
                        raise RuntimeError((completed.stderr + "\n" + completed.stdout)[-6000:])
                    probability, result = parse_response(completed.stdout)
                    record.update(status="success", flaky_probability=probability,
                                  conversation_id=result.get("conversation_id"), usage=result.get("usage"))
                except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
                    record.update(status=classify_error(str(exc)), error=str(exc))
                record["duration_seconds"] = round(time.monotonic() - start, 3)
                with log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                print(f"Run {run}, ID {ident}: {record['status']} "
                      f"{record.get('flaky_probability', '')}")
                if record["status"] == "blocked":
                    if not interactive_login(cli, "Authentication failed or account quota/credits are exhausted."):
                        return folder
                    auth_session = uuid.uuid4().hex
                    transient_failures = 0
                    continue  # Retry this exact row; never discard it or restart completed work.
                if record["status"] != "transient":
                    break
                transient_failures += 1
                if transient_failures >= 3:
                    break
                time.sleep(2 ** transient_failures)
    return folder


def compare_results(base, experiment, threshold=0.5):
    import pandas as pd
    from sklearn.metrics import accuracy_score, brier_score_loss, confusion_matrix, precision_recall_fscore_support
    base = Path(base)
    folder = base / "b0_results" / experiment
    path = folder / "predictions.jsonl"
    if not path.exists():
        raise FileNotFoundError("No saved predictions. Run cell 1 when ready.")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    # Prefer a completed success; otherwise report the latest failed attempt.
    latest = {}
    for r in records:
        key = (r["run"], r["id"])
        if key not in latest or latest[key]["status"] != "success":
            latest[key] = r
    predictions = pd.DataFrame(latest.values())
    labels = pd.read_csv(base / "sample_300_labels.csv", dtype={"id": str})[["id", "fleaky"]]
    labels = labels.rename(columns={"fleaky": "actual"})
    if not labels.actual.isin([0, 1]).all():
        raise ValueError("Invalid ground-truth labels")
    table = predictions.merge(labels, on="id", how="left", validate="many_to_one")
    if table.actual.isna().any():
        raise ValueError("Prediction IDs missing from labels")
    if "flaky_probability" not in table:
        table["flaky_probability"] = float("nan")
    example_ids = {r["id"] for r in json.loads((base / "b0_few_shot.json").read_text(encoding="utf-8"))}
    table["few_shot"] = table.id.isin(example_ids)
    table["predicted"] = table.flaky_probability.ge(threshold).astype("Int64")
    table.loc[table.status != "success", "predicted"] = pd.NA
    table["correct"] = table.predicted.eq(table.actual)
    summaries = []
    for run, group in table.groupby("run"):
        for scope in ("all", "excluding_few_shot"):
            sub = group if scope == "all" else group[~group.few_shot]
            good = sub[sub.status == "success"]
            row = {"run": run, "scope": scope, "successful": len(good),
                   "failed": len(sub) - len(good), "not_attempted": len(labels) - len(group)}
            if len(good):
                y, pred = good.actual.astype(int), good.predicted.astype(int)
                precision, recall, f1, support = precision_recall_fscore_support(y, pred, labels=[0, 1], zero_division=0)
                row.update(accuracy=accuracy_score(y, pred), brier=brier_score_loss(y, good.flaky_probability))
                for k, name in enumerate(("non_flaky", "flaky")):
                    row.update({f"{name}_precision": precision[k], f"{name}_recall": recall[k],
                                f"{name}_f1": f1[k], f"{name}_support": int(support[k])})
                row.update(zip(("tn", "fp", "fn", "tp"), confusion_matrix(y, pred, labels=[0, 1]).ravel().tolist()))
            summaries.append(row)
    metrics = pd.DataFrame(summaries)
    variation = table[table.status == "success"].groupby("id").flaky_probability.agg(["count", "mean", "std", "min", "max"])
    table.to_csv(folder / "comparison.csv", index=False)
    metrics.to_csv(folder / "metrics.csv", index=False)
    variation.to_csv(folder / "probability_variability.csv")
    aggregate = metrics.groupby("scope").agg({c: ["mean", "std"] for c in metrics if c not in {"run", "scope"}})
    aggregate.to_csv(folder / "metrics_across_runs.csv")
    return table, metrics, aggregate, variation

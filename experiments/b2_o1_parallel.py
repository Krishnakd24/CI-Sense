"""Six independent CLI lanes with a single checkpoint writer and sign-in gate."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import deque
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid

from b0_runner import SETTINGS, SCHEMA, digest, parse_response, classify_error, interactive_login
from b2_o1_runner import build_prompt


def request_one(cli, prompt, model, effort, timeout):
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="b0_inference_") as work:
            command = [cli, "--input-format", "stream-json", "--output-format", "stream-json",
                       "--model", model, "--disable-slash-commands", "--settings", json.dumps(SETTINGS),
                       "--json-schema", json.dumps(SCHEMA), "--print-timeout", f"{timeout}s"]
            if not model.endswith("(Medium)"):
                command.extend(["--effort", effort])
            elif effort != "medium":
                raise ValueError("Medium model requires medium effort")
            completed = subprocess.run(command, input=json.dumps({"event": "user", "message": {
                "content": prompt}}) + "\n", capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=work, timeout=timeout + 30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if completed.returncode:
            message = completed.stderr + "\n" + completed.stdout
            if classify_error(message) == "blocked":
                raise RuntimeError("Authentication or quota/credits require attention")
            raise RuntimeError(message[-4000:])
        probability, result = parse_response(completed.stdout)
        record = dict(status="success", flaky_probability=probability,
                      conversation_id=result.get("conversation_id"), usage=result.get("usage"))
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
        record = dict(status=classify_error(str(exc)), error=str(exc))
    record["duration_seconds"] = round(time.monotonic() - start, 3)
    return record


def run_parallel(base, selected_ids=None, n_runs=3, workers=6,
                 model="Gemini 3.8 Flash (Medium)", effort="medium",
                 experiment="b2_o1_flash_medium_v1", timeout=300, cli=None,
                 login_before_run=False, login_handler=interactive_login, request_fn=request_one):
    base = Path(base).resolve()
    if workers < 1 or n_runs < 1:
        raise ValueError("workers and n_runs must be positive")
    if Path(experiment).name != experiment or experiment in ("", ".", ".."):
        raise ValueError("Invalid experiment folder")
    data = json.loads((base / "b2_o1_data_v1.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in data}
    ids = list(by_id) if selected_ids is None else list(dict.fromkeys(map(str, selected_ids)))
    if not ids or set(ids) - set(by_id) or len(by_id) != len(data):
        raise ValueError("Invalid/duplicate input IDs")
    prompt = (base / "prompt_b2_o1.txt").read_text(encoding="utf-8")
    build_prompt(data, prompt, ids[0])
    cli = cli or shutil.which("agy") or str(Path.home() / "AppData/Local/agy/bin/agy.exe")
    folder = base / "b2_o1_results" / experiment
    folder.mkdir(parents=True, exist_ok=True)
    # OS-held lock is released even after crashes. Never run two schedulers together.
    lock_file = (folder / "parallel.lock").open("a+b")
    lock_file.seek(0)
    if os.name == "nt":
        import msvcrt
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            lock_file.close()
            raise RuntimeError("Another parallel runner already holds the experiment lock")
    try:
        config = dict(model=model, effort=effort, prompt_sha256=digest(prompt), data_sha256=digest(data),
                      settings=SETTINGS, schema=SCHEMA)
        manifest = folder / "manifest.json"
        if manifest.exists():
            old = json.loads(manifest.read_text())
            if any(old.get(k) != v for k, v in config.items()):
                raise ValueError("Prompt/model/data changed; use a new experiment")
        else:
            manifest.write_text(json.dumps(config, indent=2))
        (folder / "parallel_config.json").write_text(json.dumps(dict(workers=workers, n_runs=n_runs,
            selected_ids=ids, scheduler_sha256=digest(Path(__file__).read_text())), indent=2))
        log = folder / "predictions.jsonl"
        previous = [json.loads(s) for s in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        done = {(r["run"], r["id"]) for r in previous if r["status"] == "success"}
        assignments = [[(run, ident) for run in range(1, n_runs + 1) for ident in ids[w::workers]] for w in range(workers)]
        queues = [deque(job for job in jobs if job not in done) for jobs in assignments]
        (folder / "worker_assignments.json").write_text(json.dumps([
            {"worker": w + 1, "assigned": len(jobs), "pending": len(queues[w]), "jobs": jobs}
            for w, jobs in enumerate(assignments)], indent=2))
        auth_session = uuid.uuid4().hex
        paused = False
        stopped = False
        attempts = {}
        retry_at = {}
        pending = {}

        def status(state):
            payload = dict(state=state, workers=workers, active=len(pending),
                remaining=sum(map(len, queues)), completed_successes=len(done),
                updated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            temp = folder / "parallel_status.tmp"
            temp.write_text(json.dumps(payload, indent=2))
            temp.replace(folder / "parallel_status.json")

        if login_before_run and not login_handler(cli, "Sign in before starting six workers."):
            status("stopped")
            return folder
        with ThreadPoolExecutor(max_workers=workers) as pool:
            while any(queues) or pending:
                if paused and not pending:
                    status("awaiting_login")
                    print("ALL WORKERS PAUSED: quota/authentication. No requests are in flight.", flush=True)
                    if not login_handler(cli, "Sign in with the desired account, then choose ready to resume all six workers."):
                        stopped = True
                        break
                    auth_session = uuid.uuid4().hex
                    paused = False
                if not paused:
                    busy = {w for w, _ in pending.values()}
                    for w, queue in enumerate(queues):
                        if queue and w not in busy and time.monotonic() >= retry_at.get(w, 0):
                            run, ident = queue[0]
                            target = build_prompt(data, prompt, ident)
                            record = dict(run=run, id=ident, worker=w + 1, model=model, effort=effort,
                                auth_session=auth_session, prompt_sha256=digest(target),
                                timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                            future = pool.submit(request_fn, cli, target, model, effort, timeout)
                            pending[future] = (w, record)
                status("draining_for_login" if paused else "running")
                if not pending:
                    time.sleep(0.2)
                    continue
                finished, _ = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
                for future in finished:
                    w, record = pending.pop(future)
                    record.update(future.result())
                    key = (record["run"], record["id"])
                    attempts[key] = attempts.get(key, 0) + 1
                    record["attempt"] = attempts[key]
                    with log.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        f.flush()
                        os.fsync(f.fileno())
                    print(f"Worker {w+1}: run {key[0]}, ID {key[1]}: {record['status']} "
                          f"{record.get('flaky_probability', '')}", flush=True)
                    if record["status"] == "blocked":
                        paused = True  # Drain existing calls; never issue new ones until re-login.
                        attempts[key] = 0
                    elif record["status"] == "transient" and attempts[key] < 3:
                        retry_at[w] = time.monotonic() + 2 ** attempts[key]
                    else:
                        queues[w].popleft()
                        if record["status"] == "success":
                            done.add(key)
            status("stopped" if stopped else "finished")
        return folder
    finally:
        lock_file.close()


"""Repeat eight-worker passes until every B0 run/ID has a valid prediction."""
import json
import os
from pathlib import Path
import time

from b0_parallel import run_parallel
from b0_runner import compare_results


def unresolved(base, experiment):
    base = Path(base)
    data = json.loads((base / "b0_data_v1.json").read_text(encoding="utf-8"))
    expected = {(run, r["id"]) for run in range(1, 4) for r in data}
    log = base / "b0_results" / experiment / "predictions.jsonl"
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    good = {(r["run"], r["id"]) for r in records if r["status"] == "success"}
    return expected - good


def retry_until_complete(base, experiment="b0_flash_medium_v3", runner=run_parallel,
                         compare=compare_results, sleep=time.sleep):
    base = Path(base).resolve()
    folder = base / "b0_results" / experiment
    folder.mkdir(parents=True, exist_ok=True)
    lock = (folder / "retry_driver.lock").open("a+b")
    lock.seek(0)
    if os.name == "nt":
        import msvcrt
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            lock.close()
            raise RuntimeError("An error-retry driver is already running")
    round_number = 0

    def checkpoint(state, remaining):
        path = folder / "retry_status.tmp"
        path.write_text(json.dumps(dict(state=state, pass_number=round_number,
            workers=8, unresolved=remaining,
            updated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())), indent=2))
        path.replace(folder / "retry_status.json")

    try:
        while True:
            missing = unresolved(base, experiment)
            if not missing:
                compare(base, experiment)
                checkpoint("complete", 0)
                print("Complete: every run/ID has a valid prediction. Historical errors remain in the audit log.", flush=True)
                return
            round_number += 1
            checkpoint("running", len(missing))
            print(f"Retry pass {round_number}: {len(missing)} unresolved predictions, 8 workers.", flush=True)
            # The scheduler skips successful (run, ID) pairs, including successes from earlier retry passes.
            runner(base, selected_ids=None, n_runs=3, workers=8, experiment=experiment,
                   login_before_run=False)
            missing = unresolved(base, experiment)
            compare(base, experiment)
            status = json.loads((folder / "parallel_status.json").read_text())
            if status["state"] == "stopped":
                checkpoint("stopped", len(missing))
                print("Stopped at your request. Run this script again to resume.", flush=True)
                return
            if missing:
                delay = min(60, round_number * 10)
                checkpoint("waiting_between_passes", len(missing))
                print(f"{len(missing)} remain; next pass in {delay}s. Ctrl+C stops retries.", flush=True)
                sleep(delay)
    except KeyboardInterrupt:
        checkpoint("stopped", len(unresolved(base, experiment)))
        print("Interrupted. Saved successes will be preserved on resume.", flush=True)
    finally:
        lock.close()


if __name__ == "__main__":
    retry_until_complete(Path(__file__).resolve().parent)

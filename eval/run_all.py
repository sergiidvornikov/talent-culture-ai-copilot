"""Run every evaluation and print a one-line verdict for each:  python eval/run_all.py"""
import subprocess
import sys
from pathlib import Path

SCRIPTS = ["run_eval.py", "run_mobility_eval.py", "run_recruiting_eval.py",
           "run_comms_eval.py", "run_portfolio_eval.py", "run_spanish_eval.py"]


def main() -> int:
    here = Path(__file__).resolve().parent
    results = {}
    for name in SCRIPTS:
        proc = subprocess.run([sys.executable, str(here / name)], capture_output=True, text=True)
        results[name] = proc.returncode == 0
        if proc.returncode:
            print(proc.stdout, proc.stderr)
    for name, passed in results.items():
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Log how much CPU and memory CampusGuard (and the whole PC) uses, every few seconds, to a CSV.

    pip install psutil
    python scripts/monitor_usage.py --seconds 600 --output usage.csv

Start it, then run your 10 / 25 / 50 camera test. Afterwards open usage.csv in Excel and look at the
highest `pc_cpu_percent`. Press Ctrl+C to stop early. Matches processes whose name contains
"campusguard" (case-insensitive); change with --process.
"""
from __future__ import annotations

import argparse
import csv
import time

try:
    import psutil
except ImportError:
    raise SystemExit("This needs psutil. Run:  pip install psutil")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", type=float, default=600)
    parser.add_argument("--every", type=float, default=5)
    parser.add_argument("--process", default="campusguard")
    parser.add_argument("--output", default="usage.csv")
    args = parser.parse_args()

    needle = args.process.lower()
    cores = psutil.cpu_count(logical=True) or 1
    psutil.cpu_percent(None)
    watched: dict[int, psutil.Process] = {}
    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "pc_cpu_percent", "pc_ram_percent", "app_cpu_cores", "app_ram_mb", "app_processes"])
        end = time.time() + args.seconds
        peak = 0.0
        try:
            while time.time() < end:
                time.sleep(args.every)
                for process in psutil.process_iter(["name"]):
                    if needle in (process.info["name"] or "").lower() and process.pid not in watched:
                        watched[process.pid] = process
                        process.cpu_percent(None)
                cpu_total, ram_total, alive = 0.0, 0.0, 0
                for pid in list(watched):
                    try:
                        cpu_total += watched[pid].cpu_percent(None)
                        ram_total += watched[pid].memory_info().rss
                        alive += 1
                    except psutil.Error:
                        watched.pop(pid, None)
                pc_cpu = psutil.cpu_percent(None)
                peak = max(peak, pc_cpu)
                row = [time.strftime("%H:%M:%S"), f"{pc_cpu:.0f}", f"{psutil.virtual_memory().percent:.0f}",
                       f"{cpu_total / 100:.2f}", f"{ram_total / 1048576:.0f}", alive]
                writer.writerow(row)
                handle.flush()
                print(f"PC CPU {row[1]}% (of {cores} threads) | PC RAM {row[2]}% | app {row[3]} cores, {row[4]} MB")
        except KeyboardInterrupt:
            pass
    print(f"Done. Highest PC CPU: {peak:.0f}%. Saved {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Live event watcher: follow live.log and return the INSTANT a significant
event fires (fill / regime escalation / toxicity / error), streaming benign
notes as they pass. Blocks up to `maxwait` seconds when the tape is quiet, so
control returns periodically even with no events. This is event-driven watching
— no polling gaps — not interval snapshots."""
import re
import sys
import time

LOG = "session/live.log"
# events that demand my immediate attention -> return NOW
CRIT = re.compile(
    r"\] fill |Traceback|quoter_error|reconcile_error|task_died|divergence|"
    r"quarantine|market_blind|inflight_expired|regime=HALTED|regime=EVENT|"
    r"regime=REDUCE_ONLY|tox=0\.[1-9]|market_halted_by_meta|risk_halt|_kill"
)
# worth surfacing but not alarming -> print and keep watching
NOTE = re.compile(
    r"meta_refreshed|user_ws_reconnected|market_ws_dropped|position_forced|"
    r"untracked_positions|book_drift|market_halted|pagination"
)

maxwait = float(sys.argv[1]) if len(sys.argv) > 1 else 540.0
f = open(LOG)
f.seek(0, 2)  # tail from end
start = time.time()
fired = False
while time.time() - start < maxwait:
    line = f.readline()
    if not line:
        time.sleep(0.4)
        continue
    if "HTTP Request" in line or "heartbeats" in line:
        continue
    if CRIT.search(line):
        print("!! CRIT ", line.strip()[:230], flush=True)
        fired = True
        break
    if NOTE.search(line):
        print(".. note ", line.strip()[:190], flush=True)
elapsed = int(time.time() - start)
print(f"[{'CRITICAL — reacting' if fired else f'quiet {elapsed}s — re-arming'}]")

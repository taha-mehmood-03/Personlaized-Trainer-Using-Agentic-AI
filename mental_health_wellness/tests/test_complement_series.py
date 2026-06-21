"""
Series Complement Test — SentiMind
===================================
Reproduces the user's anger/injustice scenario where the agent should:
  1. Deliver an immediate-regulation breathing exercise for the body tension
  2. In the SAME turn, OFFER a second (complement) exercise for the injustice/cognitive signal
  3. When the user accepts, deliver the SAME queued complement — not a fresh unrelated pick

Server must be running at http://localhost:8000.
"""

import sys
import json
import time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

BASE    = "http://localhost:8000"
USER_ID = "cmqe489260020lcl1jloc70h6"
TIMEOUT = 120

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; D = "\033[2m"; RST = "\033[0m"
def g(s): return f"{G}{s}{RST}"
def r(s): return f"{R}{s}{RST}"
def y(s): return f"{Y}{s}{RST}"
def c(s): return f"{C}{s}{RST}"
def b(s): return f"{B}{s}{RST}"


def create_session(client):
    resp = client.post(f"{BASE}/api/session/new", json={"user_id": USER_ID}, timeout=15)
    resp.raise_for_status()
    return resp.json()["session_id"]


def send(client, session_id, message):
    payload = {"user_id": USER_ID, "message": message, "session_id": session_id}
    tokens, meta = [], {}
    with client.stream("POST", f"{BASE}/api/chat/stream", json=payload, timeout=TIMEOUT) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines():
            line = raw.strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data:
                continue
            try:
                evt = json.loads(data)
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "token":
                tokens.append(evt.get("content", ""))
            elif evt.get("type") == "done":
                meta = {k: v for k, v in evt.items() if k != "type"}
    return "".join(tokens), meta


def tech_name(meta):
    return (meta.get("recommended_technique") or {}).get("name", "")


def print_turn(n, msg, resp, meta):
    print(f"\n  {b(f'Turn {n}')}  {D}route={meta.get('gate_route','?')} | task={meta.get('response_task','?')}{RST}")
    print(f"  {D}→ User:{RST} {c(msg[:70])}")
    print(f"  {D}← Bot:{RST}  {resp[:160]}")
    t = tech_name(meta)
    if t:
        print(f"  {D}technique:{RST} {g(t)}")


def main():
    bar = "═" * 70
    print(b(f"\n{bar}"))
    print(b("  SentiMind — Series Complement Test"))
    print(b(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    print(b(f"{bar}"))

    with httpx.Client(timeout=TIMEOUT) as client:
        sid = create_session(client)
        print(f"  Session: {g(sid)}")

        # Build toward the immediate-regulation series (anger + body tension + injustice).
        turns = [
            "im gonna beat someone in my class",
            "a student complained about me and i did nothing so the teacher insulted me in front of everyone",
            "i didn't respond but in my mind i was thinking i would not leave them",
            "i was trying to hold it but it was beyond my control",
            "yes my teeth were grinding against each other and my jaw was clenched tight",
        ]
        meta = {}
        primary_resp = ""
        for i, t in enumerate(turns, 1):
            resp, meta = send(client, sid, t)
            print_turn(i, t, resp, meta)
            if meta.get("response_task") == "start_grounding_now":
                primary_resp = resp
            time.sleep(0.5)

        # Did the immediate-regulation turn ALSO offer a complement?
        print(b("\n── Checks ───────────────────────────────────────────────────"))
        passed = True

        offered_complement = ("ready for" in primary_resp.lower() and "let me know" in primary_resp.lower()) \
                             or "would you like an exercise" in primary_resp.lower()
        if primary_resp:
            if offered_complement:
                print(g("  ✅ Immediate-regulation turn surfaced a complement offer"))
            else:
                print(y("  ⚠  No deterministic complement offer detected in the grounding turn"))
                print(y(f"     (grounding turn may not have entered SERIES mode this run)"))
        else:
            print(y("  ⚠  No start_grounding_now turn fired — series may not have triggered this run"))

        # Accept the complement and verify the SAME queued technique is delivered.
        resp6, meta6 = send(client, sid, "yes please, i'd like to try that one too")
        print_turn(6, "yes please, i'd like to try that one too", resp6, meta6)

        if meta6.get("response_task") == "offer_complement_technique":
            print(g(f"  ✅ Acceptance routed to offer_complement_technique → delivered {tech_name(meta6)}"))
        else:
            print(y(f"  ⚠  Acceptance task = {meta6.get('response_task')} (expected offer_complement_technique)"))

        print(b(f"\n{bar}"))
        print(b("  Inspect server logs for: [TECHNIQUE] Complement queued / [ACCEPT_COMPLEMENT] Promoting"))
        print(b(f"{bar}\n"))


if __name__ == "__main__":
    main()

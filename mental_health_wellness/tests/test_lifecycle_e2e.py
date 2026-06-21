"""
E2E Lifecycle Test — SentiMind
===============================
Tests all 8 lifecycle paths against the running backend at http://localhost:8000.
Each path runs in its own fresh session (same user ID).

Usage:
    python tests/test_lifecycle_e2e.py            # run all paths
    python tests/test_lifecycle_e2e.py --path 2   # run one path

Server must be running at http://localhost:8000 before executing.
"""

import sys
import io
import json
import time
import argparse
from datetime import datetime

# Force UTF-8 output on Windows so box-drawing chars / emojis don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx

# ─── Config ──────────────────────────────────────────────────────────────────

BASE = "http://localhost:8000"
USER_ID = "cmqe489260020lcl1jloc70h6"
REF_SESSION = "cmqlq2npu0001rg23yaya9q2p"   # existing session, used for Path 7

TIMEOUT = 120   # seconds — LLM calls can take a while

# ─── ANSI colours ────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def green(s):  return f"{GREEN}{s}{RESET}"
def red(s):    return f"{RED}{s}{RESET}"
def yellow(s): return f"{YELLOW}{s}{RESET}"
def cyan(s):   return f"{CYAN}{s}{RESET}"
def bold(s):   return f"{BOLD}{s}{RESET}"
def dim(s):    return f"{DIM}{s}{RESET}"

# ─── SSE helpers ─────────────────────────────────────────────────────────────

def stream_message(client: httpx.Client, session_id: str, message: str):
    """
    POST to /api/chat/stream and consume the SSE response.
    Returns (response_text, metadata_dict).
    """
    payload = {
        "user_id": USER_ID,
        "message": message,
        "session_id": session_id,
    }
    tokens = []
    metadata = {}

    with client.stream(
        "POST",
        f"{BASE}/api/chat/stream",
        json=payload,
        timeout=TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            line = raw_line.strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if not data_str:
                continue
            try:
                evt = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            if evt.get("type") == "token":
                tokens.append(evt.get("content", ""))
            elif evt.get("type") == "done":
                # Server merges metadata directly into the event dict (not nested under "metadata")
                metadata = {k: v for k, v in evt.items() if k != "type"}

    return "".join(tokens), metadata


def create_session(client: httpx.Client) -> str:
    """POST /api/session/new and return the new session_id."""
    resp = client.post(f"{BASE}/api/session/new", json={"user_id": USER_ID}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data["session_id"]


# ─── Printing helpers ─────────────────────────────────────────────────────────

def _trunc(s: str, n: int = 45) -> str:
    s = (s or "").replace("\n", " ")
    return (s[:n] + "…") if len(s) > n else s

def print_turn(turn_num: int, message: str, response: str, meta: dict):
    gate       = meta.get("gate_route", "?")
    intent     = meta.get("intent", "?")
    task       = meta.get("response_task", "?")
    stage      = meta.get("conversation_stage", "?")
    phase      = meta.get("conversation_phase", "?")
    emotion    = meta.get("emotion", "?")
    intensity  = meta.get("intensity") or meta.get("fused_intensity", 0)
    tech_flag  = meta.get("technique_offered_this_turn", False)
    crisis     = meta.get("crisis_detected", False)
    node_trace = meta.get("node_trace", [])
    tech_name  = (meta.get("recommended_technique") or {}).get("name", "")
    alts       = meta.get("alternative_techniques", [])

    tech_str = f"{green('✓ ' + tech_name)}" if tech_flag else dim("—")
    crisis_str = red("🚨 YES") if crisis else dim("no")

    print(f"\n  {bold(f'Turn {turn_num}')}")
    print(f"  {dim('→ User:')}    {cyan(_trunc(message))}")
    print(f"  {dim('← Bot:')}     {_trunc(response)}")
    print(f"  {dim('gate_route:')}        {yellow(gate)}")
    print(f"  {dim('intent:')}            {intent}")
    print(f"  {dim('response_task:')}     {bold(task)}")
    print(f"  {dim('stage/phase:')}       {stage} / {phase}")
    print(f"  {dim('emotion:')}           {emotion} (intensity={intensity:.2f})" if isinstance(intensity, (int, float)) else f"  {dim('emotion:')}           {emotion}")
    print(f"  {dim('technique:')}         {tech_str}")
    if alts:
        alt_names = [a.get("name", "?") for a in alts[:3]]
        print(f"  {dim('alternatives:')}     {', '.join(alt_names)}")
    print(f"  {dim('crisis:')}            {crisis_str}")
    print(f"  {dim('nodes:')}             {' → '.join(node_trace[-4:]) if node_trace else '?'}")


def print_path_header(path_num: int, path_name: str):
    bar = "═" * 70
    print(f"\n{BOLD}{CYAN}{bar}{RESET}")
    print(f"{BOLD}{CYAN}  PATH {path_num}: {path_name}{RESET}")
    print(f"{BOLD}{CYAN}{bar}{RESET}")


def print_summary(path_num: int, path_name: str, turn_results: list):
    """
    turn_results: list of (message, meta, checks_passed, failures)
    """
    total_checks = sum(len(checks) + len(failures) for _, _, checks, failures in turn_results)
    passed = sum(len(checks) for _, _, checks, failures in turn_results)
    failed = sum(len(failures) for _, _, checks, failures in turn_results)

    print(f"\n  {bold('SUMMARY — Path ' + str(path_num) + ': ' + path_name)}")
    print(f"  {'─'*60}")
    header = f"  {'Turn':<5} {'Message':<47} {'Task':<30} {'Stage':<12} {'Tech'}"
    print(dim(header))
    for i, (msg, meta, checks, failures) in enumerate(turn_results, 1):
        task   = (meta.get("response_task") or "?")[:28]
        stage  = (meta.get("conversation_stage") or "?")[:10]
        tech   = "✓" if meta.get("technique_offered_this_turn") else "—"
        status = green("✓") if not failures else red("✗")
        print(f"  {status} {i:<4} {_trunc(msg, 45):<47} {task:<30} {stage:<12} {tech}")

    for i, (msg, meta, checks, failures) in enumerate(turn_results, 1):
        for fail in failures:
            print(red(f"  ❌ Turn {i} FAILED: {fail}"))

    if failed == 0:
        print(green(f"\n  ✅ ALL CHECKS PASSED ({passed}/{total_checks})"))
    else:
        print(red(f"\n  ❌ {failed} CHECK(S) FAILED, {passed}/{total_checks} passed"))
    print()


# ─── Check evaluator ─────────────────────────────────────────────────────────

def evaluate_checks(meta: dict, expected: dict) -> tuple[list, list]:
    """Returns (passed_descriptions, failure_descriptions)."""
    passed, failed = [], []
    for key, expected_val in expected.items():
        actual = meta.get(key)

        if isinstance(expected_val, bool):
            ok = bool(actual) == expected_val
        elif isinstance(expected_val, str):
            ok = str(actual or "").lower() == expected_val.lower()
        elif isinstance(expected_val, list):
            # check: expected values are subset of actual list
            ok = all(v in (actual or []) for v in expected_val)
        elif callable(expected_val):
            ok = expected_val(actual)
        else:
            ok = actual == expected_val

        desc = f"{key}={expected_val!r} (got {actual!r})"
        if ok:
            passed.append(desc)
        else:
            failed.append(desc)
    return passed, failed


# ─── Core runner ─────────────────────────────────────────────────────────────

def run_path(
    client: httpx.Client,
    path_num: int,
    path_name: str,
    session_id: str,
    turns: list,
) -> bool:
    """
    turns: list of dicts with keys:
        message  — str to send (or None = adaptive)
        adaptive — callable(meta_from_prev_turn) -> str (optional)
        checks   — dict of expected field values
        stop_if  — callable(meta) -> bool (end path early if True)
    Returns True if all checks passed.
    """
    print_path_header(path_num, path_name)
    print(f"  Session: {dim(session_id)}\n")

    turn_results = []
    prev_meta = {}

    for i, turn in enumerate(turns, 1):
        # Resolve message (static or adaptive)
        if "adaptive" in turn and callable(turn["adaptive"]):
            message = turn["adaptive"](prev_meta)
            if message is None:
                print(dim(f"  Turn {i}: adaptive → skipped (condition not met)"))
                continue
        else:
            message = turn["message"]

        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  {dim(f'[{ts}]')} Sending turn {i}…", end="", flush=True)
        t0 = time.time()
        try:
            response_text, meta = stream_message(client, session_id, message)
        except Exception as exc:
            print(red(f" ERROR: {exc}"))
            turn_results.append((message, {}, [], [f"request failed: {exc}"]))
            continue
        elapsed = time.time() - t0
        print(f" {dim(f'{elapsed:.1f}s')}")

        print_turn(i, message, response_text, meta)

        checks   = turn.get("checks", {})
        passed_c, failed_c = evaluate_checks(meta, checks)
        turn_results.append((message, meta, passed_c, failed_c))

        if failed_c:
            for f in failed_c:
                print(red(f"    ❌ CHECK FAILED: {f}"))
        elif checks:
            print(green(f"    ✅ {len(passed_c)} check(s) passed"))

        prev_meta = meta

        # End path early if stop condition met
        if "stop_if" in turn and turn["stop_if"](meta):
            print(yellow(f"  ⏹  stop_if triggered — ending path early at turn {i}"))
            break

    print_summary(path_num, path_name, turn_results)
    return all(not r[3] for r in turn_results)


# ─── Path definitions ────────────────────────────────────────────────────────

def _is_context_question(meta):
    return meta.get("response_task") in {
        "ask_question", "ask_one_missing_context_question",
        "ask_next_context_question", "ask_reflection_question",
    }

def _is_technique_offered(meta):
    return bool(meta.get("technique_offered_this_turn"))

def _adaptive_context_answer(prev_meta):
    """If bot asked a context question, answer it; else skip."""
    if _is_context_question(prev_meta):
        return "It has been about 2 weeks. My final exams are next week and I keep worrying I will fail."
    return None   # skip this turn

def _adaptive_accept_or_skip(prev_meta):
    """Accept a technique if offered, else skip."""
    if prev_meta.get("response_task") in {"ask_permission_before_technique", "offer_one_technique"} \
       or "technique" in (prev_meta.get("response_task") or "").lower():
        return "yes please share the technique with me"
    if _is_technique_offered(prev_meta):
        return "thank you that was great, the technique really helped"
    return None


PATHS = [
    # ── Path 1 ── Chitchat ────────────────────────────────────────────────────
    {
        "num": 1,
        "name": "Casual / Chitchat",
        "use_ref_session": False,
        "turns": [
            {
                "message": "hey how are you",
                "checks": {"gate_route": "chitchat"},
            },
            {
                "message": "my name is taha and I am a final year student",
                "checks": {
                    "gate_route": "chitchat",
                    "technique_offered_this_turn": False,
                },
            },
            {
                "message": "what is 2 plus 2",
                "checks": {"technique_offered_this_turn": False},
            },
        ],
    },

    # ── Path 2 ── Single-domain → accept → warm close ─────────────────────────
    {
        "num": 2,
        "name": "Single-domain: Disclosure → Technique → Warm Close",
        "use_ref_session": False,
        "turns": [
            {
                "message": "I have been really anxious lately. I cannot sleep at night and feel tense all day. I keep worrying about everything.",
                "checks": {"gate_route": "therapeutic"},
            },
            {
                # adaptive: answer context question if asked, else send context anyway
                "message": "It started about two weeks ago when my exams were announced. I feel a tight chest and racing thoughts especially at night. It is affecting my ability to study.",
                "checks": {},
            },
            {
                # adaptive: if technique already offered last turn, say yes; else explicitly ask
                "adaptive": lambda prev: (
                    "yes please share a technique with me"
                    if prev.get("response_task") in {
                        "ask_permission_before_technique", "offer_one_technique",
                        "start_grounding_now"
                    }
                    else "yes I would like to try a technique to help me calm down"
                ),
                "checks": {},
            },
            {
                # After technique is delivered, say it helped
                "adaptive": lambda prev: (
                    "thank you that really helped me feel much calmer, I feel better now"
                    if _is_technique_offered(prev)
                    else "I feel a bit better after reading that, thank you"
                ),
                "checks": {"conversation_stage": "RECOVERY"},
            },
            {
                "message": "the breathing step was the most helpful part. I feel much better now, thank you so much",
                "checks": {"response_task": "warm_close_and_invite"},
                "stop_if": lambda m: m.get("response_task") == "warm_close_and_invite",
            },
        ],
    },

    # ── Path 3 ── Multi-domain → immediate + complement ───────────────────────
    {
        "num": 3,
        "name": "Multi-domain: Immediate Breathing + Complement CBT",
        "use_ref_session": False,
        "turns": [
            {
                "message": (
                    "I am having a big conflict with my brother and we haven't spoken in days. "
                    "I keep ruminating about the fight all day and cannot stop. "
                    "I also cannot sleep and feel very anxious and on edge all the time."
                ),
                "checks": {
                    "gate_route": "therapeutic",
                },
            },
            {
                "message": "yes I need immediate help, I feel overwhelmed right now",
                "checks": {},
            },
            {
                "adaptive": lambda prev: (
                    "yes please"
                    if prev.get("response_task") in {
                        "ask_permission_before_technique", "offer_one_technique",
                        "start_grounding_now", "offer_complement_technique"
                    }
                    else "thank you, what else can I do about the rumination and the conflict"
                ),
                "checks": {},
            },
            {
                "message": "ok I finished the breathing exercise, what else can I do to handle the rumination and family conflict",
                "checks": {},
            },
            {
                "message": "yes please share that technique with me",
                "checks": {},
            },
        ],
    },

    # ── Path 4 ── Explicit technique request ──────────────────────────────────
    {
        "num": 4,
        "name": "Explicit Technique Request",
        "use_ref_session": False,
        "turns": [
            {
                "message": "I want to try the 4-7-8 breathing exercise right now",
                "checks": {
                    "gate_route": "technique_request",
                    "technique_offered_this_turn": True,
                },
            },
            {
                "message": "that was great, I feel calmer now thank you",
                "checks": {"conversation_stage": "RECOVERY"},
            },
            {
                "message": "the exhale step really helped me the most, I feel much better now",
                "checks": {"response_task": "warm_close_and_invite"},
                "stop_if": lambda m: m.get("response_task") == "warm_close_and_invite",
            },
        ],
    },

    # ── Path 5 ── Technique decline ───────────────────────────────────────────
    {
        "num": 5,
        "name": "Technique Decline",
        "use_ref_session": False,
        "turns": [
            {
                "message": "I am really stressed about my work presentation tomorrow, feeling completely overwhelmed and I can't focus",
                "checks": {"gate_route": "therapeutic"},
            },
            {
                "message": "no thanks I do not want any exercises or techniques right now",
                "checks": {
                    "response_task": "handle_technique_rejection",
                },
            },
            {
                "message": "I just want to talk about it and feel heard",
                "checks": {"technique_offered_this_turn": False},
            },
        ],
    },

    # ── Path 6 ── Crisis ──────────────────────────────────────────────────────
    {
        "num": 6,
        "name": "Crisis Detection",
        "use_ref_session": False,
        "turns": [
            {
                "message": "I feel completely hopeless. I have been thinking about hurting myself and I don't see a way out",
                "checks": {
                    "crisis_detected": True,
                },
            },
            {
                "message": "I don't know what to do, I feel like nobody cares",
                "checks": {
                    "crisis_detected": True,
                    "technique_offered_this_turn": False,
                },
            },
        ],
    },

    # ── Path 7 ── Memory query ────────────────────────────────────────────────
    {
        "num": 7,
        "name": "Memory Query (using existing session)",
        "use_ref_session": True,
        "turns": [
            {
                "message": "what techniques have we tried in our previous sessions?",
                "checks": {
                    "gate_route": lambda v: v in ("memory_query", "contextual_followup", "therapeutic"),
                },
            },
            {
                "message": "can you remind me which one helped me the most last time?",
                "checks": {},
            },
        ],
    },

    # ── Path 8 ── User-initiated exit ─────────────────────────────────────────
    {
        "num": 8,
        "name": "User-Initiated Exit",
        "use_ref_session": False,
        "turns": [
            {
                "message": "I feel really overwhelmed with work today",
                "checks": {"gate_route": "therapeutic"},
            },
            {
                "message": "actually I have to go now, thanks bye",
                "checks": {
                    "response_task": "immediate_close",
                },
            },
        ],
    },
]


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SentiMind lifecycle E2E test")
    parser.add_argument("--path", type=int, default=None, help="Run only this path number (1-8)")
    args = parser.parse_args()

    paths_to_run = [p for p in PATHS if args.path is None or p["num"] == args.path]
    if not paths_to_run:
        print(red(f"No path with number {args.path}"))
        sys.exit(1)

    print(bold(f"\n{'═'*70}"))
    print(bold(f"  SentiMind E2E Lifecycle Test"))
    print(bold(f"  User ID : {USER_ID}"))
    print(bold(f"  Server  : {BASE}"))
    print(bold(f"  Paths   : {', '.join(str(p['num']) for p in paths_to_run)}"))
    print(bold(f"  Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    print(bold(f"{'═'*70}\n"))

    # Verify server is reachable
    try:
        with httpx.Client(timeout=5) as hc:
            hc.get(f"{BASE}/health")
    except Exception:
        try:
            with httpx.Client(timeout=5) as hc:
                hc.get(f"{BASE}/api/health")
        except Exception as exc:
            print(red(f"❌ Cannot reach server at {BASE}: {exc}"))
            print(yellow("   Make sure the backend is running before running this test."))
            sys.exit(1)

    all_passed = True
    path_results = []

    with httpx.Client(timeout=TIMEOUT) as client:
        for path_def in paths_to_run:
            # Session setup
            if path_def.get("use_ref_session"):
                session_id = REF_SESSION
                print(yellow(f"  Using reference session: {session_id}"))
            else:
                print(f"  Creating new session for path {path_def['num']}…", end="", flush=True)
                try:
                    session_id = create_session(client)
                    print(green(f" {session_id}"))
                except Exception as exc:
                    print(red(f" FAILED: {exc}"))
                    all_passed = False
                    path_results.append((path_def["num"], path_def["name"], False))
                    continue

            passed = run_path(
                client,
                path_def["num"],
                path_def["name"],
                session_id,
                path_def["turns"],
            )
            all_passed = all_passed and passed
            path_results.append((path_def["num"], path_def["name"], passed))

    # Final report
    print(bold(f"\n{'═'*70}"))
    print(bold("  FINAL REPORT"))
    print(bold(f"{'═'*70}"))
    for num, name, ok in path_results:
        status = green("✅ PASS") if ok else red("❌ FAIL")
        print(f"  {status}  Path {num}: {name}")
    print(bold(f"{'═'*70}"))
    if all_passed:
        print(green(bold("\n  ALL PATHS PASSED ✅\n")))
    else:
        print(red(bold("\n  SOME PATHS FAILED ❌ — check the output above.\n")))
        sys.exit(1)


if __name__ == "__main__":
    main()

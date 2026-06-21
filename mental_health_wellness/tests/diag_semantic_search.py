"""
Semantic Search Diagnostic — SentiMind
=======================================
Empirically measures whether pgvector technique retrieval differentiates the
right exercises for a given clinical context. Prints RAW cosine similarities so
we can see if the semantic signal is meaningful or flat/inert.

Tests two query styles for each scenario:
  A. Structured tag query  (what the system builds today: "emotion: X | ...")
  B. Natural-language query (how the technique docs are actually written)

If style B produces clearly higher / better-separated similarities than style A,
that confirms a query/document style mismatch is crippling semantic rerank.

Run:  python tests/diag_semantic_search.py
Requires the embeddings model + pgvector DB to be reachable.
"""

import sys
import asyncio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mental_health_wellness.memory.pgvector_store import search_embeddings

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; D = "\033[2m"; RST = "\033[0m"


# (label, expected-good technique substrings, structured query, natural query)
SCENARIOS = [
    (
        "Acute anger at teacher (injustice, body tension)",
        ["tipp", "box breathing", "stop", "4-7-8", "check the facts", "cognitive restructuring"],
        ("emotion: anger | intensity: 0.85 | primary feeling: anger | "
         "secondary feelings: feeling_disrespected, irritability, distress | "
         "symptoms: body_tension | behaviors: impulsivity, rumination | "
         "context tags: teacher_conflict, school_conflict"),
        ("I'm furious — a teacher humiliated me in front of the class and my jaw is "
         "clenched and I feel like I could lash out. I need to calm down right now."),
    ),
    (
        "Bedtime exam rumination (anxiety, sleep)",
        ["worry time", "brain dump", "4-7-8", "mindfulness of thoughts", "thought record"],
        ("emotion: anxiety | intensity: 0.7 | primary feeling: worry | "
         "secondary feelings: racing_thoughts, fear_of_failure | "
         "symptoms: sleep_difficulty | behaviors: rumination | "
         "context tags: exam_week, bedtime_rumination"),
        ("I can't sleep before my exam — my mind keeps racing with worst-case "
         "thoughts about failing and I just lie there overthinking everything."),
    ),
    (
        "Depression / avoidance (low mood, procrastination)",
        ["activity scheduling", "micro", "behavioral", "pleasant activity", "routine"],
        ("emotion: sadness | intensity: 0.6 | primary feeling: low_mood | "
         "secondary feelings: anhedonia, hopelessness | "
         "behaviors: avoidance, procrastination | context tags: social_isolation"),
        ("I've got no energy and everything feels pointless. I keep putting off even "
         "tiny tasks and I haven't left the house or done anything I used to enjoy."),
    ),
]


def fmt_row(i, name, sim, good):
    mark = G + "✓" + RST if good else " "
    color = G if sim >= 0.50 else (Y if sim >= 0.35 else R)
    bar = "█" * int(max(0, sim) * 40)
    return f"    {i:>2}. {mark} {color}{sim:+.3f}{RST}  {name[:34]:<34} {D}{bar}{RST}"


def is_good(name, good_subs):
    n = name.lower()
    return any(s in n for s in good_subs)


async def run_query(label, query, good_subs):
    rows = await search_embeddings(query=query, source_types=["technique"], limit=10)
    if not rows:
        print(R + "    (no rows — pgvector returned nothing for this query)" + RST)
        return None
    sims = []
    print(f"  {D}query:{RST} {query[:90]}…")
    good_in_top3 = 0
    for i, row in enumerate(rows, 1):
        name = (row.get("metadata") or {}).get("name") or (row.get("content") or "")[:34]
        sim = float(row.get("similarity") or 0.0)
        good = is_good(name, good_subs)
        if good and i <= 3:
            good_in_top3 += 1
        sims.append(sim)
        print(fmt_row(i, name, sim, good))
    spread = max(sims) - min(sims)
    print(f"  {D}top similarity={max(sims):.3f}  spread={spread:.3f}  "
          f"clinically-good in top-3: {good_in_top3}/3{RST}")
    return {"top": max(sims), "spread": spread, "good_top3": good_in_top3}


async def main():
    print(B + "\n══ Semantic Search Diagnostic (raw pgvector cosine similarity) ══" + RST)
    print(D + "  ✓ = clinically-appropriate technique for the scenario" + RST)
    print(D + "  green ≥0.50  yellow ≥0.35  red <0.35\n" + RST)

    agg = {"A": [], "B": []}
    for label, good_subs, q_struct, q_natural in SCENARIOS:
        print(B + f"\n── {label} ──" + RST)
        print(C + "  [A] Structured tag query (current system format):" + RST)
        ra = await run_query(label, q_struct, good_subs)
        print(C + "\n  [B] Natural-language query:" + RST)
        rb = await run_query(label, q_natural, good_subs)
        if ra:
            agg["A"].append(ra)
        if rb:
            agg["B"].append(rb)

    print(B + "\n\n══ Summary ══" + RST)
    for style in ("A", "B"):
        rows = agg[style]
        if not rows:
            continue
        avg_top = sum(r["top"] for r in rows) / len(rows)
        avg_spread = sum(r["spread"] for r in rows) / len(rows)
        good = sum(r["good_top3"] for r in rows)
        label = "Structured tag" if style == "A" else "Natural language"
        print(f"  {label:<18}  avg_top_sim={avg_top:.3f}  avg_spread={avg_spread:.3f}  "
              f"good-in-top3={good}/{len(rows)*3}")
    print(D + "\n  Interpretation: if avg_top_sim is low (<0.5) and spread is small (<0.15),\n"
          "  semantic rerank is effectively inert — selection is driven by the\n"
          "  hardcoded context-boost tables, not by meaning. If [B] >> [A], the\n"
          "  query/document style mismatch is the cause.\n" + RST)


if __name__ == "__main__":
    asyncio.run(main())

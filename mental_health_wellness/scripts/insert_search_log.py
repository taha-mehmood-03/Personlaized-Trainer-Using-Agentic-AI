"""
Inserts the SEMANTIC SEARCH RESULTS box log into technique_selector_node.py
right after  technique_candidates = filtered[:8]  (line 2007).
"""

path = 'src/mental_health_wellness/nodes/technique_selector_node.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the exact line to insert after
marker = '        technique_candidates = filtered[:8]\n'
insert_after = None
for idx, line in enumerate(lines):
    if line == marker:
        insert_after = idx
        break

if insert_after is None:
    raise RuntimeError("Marker line not found!")

new_block = """\
\n\
        # ── SEMANTIC SEARCH RESULTS log ────────────────────────────────\n\
        _sbar = "─" * 64\n\
        print(f"\\n┌{_sbar}┐")\n\
        print(f"│  SEMANTIC SEARCH RESULTS  ({elapsed_ms}ms) — {len(top3)} raw hits, {len(filtered)} after filter")\n\
        print(f"├{_sbar}┤")\n\
        for _ri, _rc in enumerate(technique_candidates, 1):\n\
            _rc_reasons = "; ".join((_rc.get("score_reasons") or [])[:3]) or "semantic match"\n\
            _rc_int = f"{_rc.get('min_intensity', 0):.0%}–{_rc.get('max_intensity', 1):.0%}"\n\
            print(f"│  {_ri:>2}. {_rc.get('name', '?'):<35} [{_rc.get('category', '?')}]")\n\
            print(f"│      Reasons : {_rc_reasons[:80]}")\n\
            print(f"│      Intensity: {_rc_int}")\n\
        print(f"└{_sbar}┘")\n\
        # ───────────────────────────────────────────────────────────────\n\
"""

new_lines = lines[:insert_after + 1] + [new_block] + lines[insert_after + 1:]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Done — inserted log block after line {insert_after + 1} ({marker.strip()!r})")

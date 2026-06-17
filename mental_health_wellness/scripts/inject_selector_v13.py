"""
Script to inject v13.0 technique boosting and filtering into technique_selector_node.py.
"""

target = r'E:\FYP\mental_health_wellness\src\mental_health_wellness\nodes\technique_selector_node.py'

with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

marker = '        technique_candidates = filtered[:8]'

rerank_code = """        # ============================================
        # v13.0: RERANK & FILTER CANDIDATES BY USER GOAL
        # Boost category scoring when latest_user_need is set.
        # Force breathing/grounding for immediate_regulation_request.
        # ============================================
        latest_user_need = state.get("latest_user_need")
        immediate_regulation_request = state.get("immediate_regulation_request", False)
        response_task = state.get("response_task", "")

        _GOAL_CATEGORY_BOOST = {
            "calm_body_now":              ["breathing", "grounding"],
            "reach_out_to_friend":        ["behavioral_activation", "social_skills"],
            "write_simple_message":       ["behavioral_activation", "social_skills"],
            "know_where_to_start":        ["behavioral_activation", "cbt"],
            "break_project_into_steps":   ["behavioral_activation", "cbt"],
            "stop_overthinking_at_night": ["dbt", "mindfulness", "cbt"],
            "sleep_better":               ["mindfulness", "breathing"],
        }

        if immediate_regulation_request or response_task == "start_grounding_now":
            reg_filtered = [
                t for t in filtered
                if (t.get("category") or "").lower() in ("breathing", "grounding")
            ]
            if reg_filtered:
                filtered = reg_filtered
                print(f"[TECHNIQUE] v13.0: Filtered shortlist to breathing/grounding only (immediate regulation/grounding task)")
            else:
                print("[TECHNIQUE] v13.0: No breathing/grounding in shortlist, prioritizing them at top")
                filtered = sorted(
                    filtered,
                    key=lambda x: 0 if (x.get("category") or "").lower() in ("breathing", "grounding") else 1
                )
        elif latest_user_need in _GOAL_CATEGORY_BOOST:
            boosted_categories = _GOAL_CATEGORY_BOOST[latest_user_need]
            def _sort_key(t):
                cat = (t.get("category") or "").lower()
                for idx, b_cat in enumerate(boosted_categories):
                    if b_cat in cat:
                        return idx
                return len(boosted_categories)
            
            filtered = sorted(filtered, key=_sort_key)
            print(f"[TECHNIQUE] v13.0: Reranked candidates for user need '{latest_user_need}' using categories: {boosted_categories}")

"""

if 'v13.0: RERANK & FILTER CANDIDATES BY USER GOAL' not in content:
    content = content.replace(marker, rerank_code + "\n" + marker)
    with open(target, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Technique selector v13.0 changes injected successfully")
else:
    print("Technique selector v13.0 changes already present")

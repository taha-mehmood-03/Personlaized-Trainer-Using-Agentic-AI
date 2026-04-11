"""
SentiMind v5.3 Latency Benchmark
Tests pipeline speed with models pre-loaded (simulates warm server).
Compare output against v5.2 baseline to confirm latency improvements.
"""

import asyncio
import sys
import time
sys.path.insert(0, 'src')

async def main():
    # ---- PRELOAD (one-time, same as server startup) ----
    print("=" * 60)
    print("[BENCHMARK] Preloading models (simulates server startup)...")
    print("=" * 60)
    
    t0 = time.time()
    
    from mental_health_wellness.tools.mood_tools import preload_emotion_model
    from mental_health_wellness.llm.llm_classifier import _get_crisis_classifier
    from mental_health_wellness.llm.groq_llm import get_llm_manager
    
    preload_emotion_model()
    _get_crisis_classifier()
    get_llm_manager()
    
    preload_ms = int((time.time() - t0) * 1000)
    print(f"\n[BENCHMARK] ✅ Preload complete in {preload_ms}ms (one-time cost)")
    print("=" * 60)
    
    from mental_health_wellness.agent.graph import chat_with_agent
    
    tests = [
        ("Obvious Venting (heuristic fast-path)",    "i feel so stressed out today everything is falling apart",  "bench_1"),
        ("Technique Request (heuristic fast-path)",  "can you guide me through a breathing exercise",             "bench_2"),
        ("Ambiguous (LLM intent needed)",            "maybe things will get better I don't know",                 "bench_3"),
        ("Casual Chitchat (fast path)",              "hey what's up",                                             "bench_4"),
    ]
    
    results = []
    
    for label, msg, sid in tests:
        print(f"\n\n{'=' * 60}")
        print(f"[BENCHMARK] TEST: {label}")
        print(f"[BENCHMARK] Message: \"{msg}\"")
        print(f"{'=' * 60}")
        
        res = await chat_with_agent("benchmark_user", msg, sid)
        
        ms = res.get("processing_time_ms", 0)
        trace = res.get("node_trace", [])
        strategy = res.get("conversation_strategy", "?")
        
        results.append((label, ms, strategy, len(trace)))
        print(f"\n[BENCHMARK] ⏱️  {label}: {ms}ms | Strategy: {strategy} | Nodes: {len(trace)}")
    
    # ---- SUMMARY ----
    print("\n\n" + "=" * 60)
    print("[BENCHMARK] 📊 RESULTS SUMMARY")
    print("=" * 60)
    print(f"{'Test':<45} {'Time':>8} {'Strategy':>20} {'Nodes':>6}")
    print("-" * 83)
    
    for label, ms, strategy, node_count in results:
        color = "🟢" if ms < 3000 else "🟡" if ms < 5000 else "🔴"
        print(f"{color} {label:<43} {ms:>6}ms {strategy:>20} {node_count:>6}")
    
    avg = sum(r[1] for r in results) / len(results)
    print("-" * 83)
    print(f"   {'AVERAGE':<43} {int(avg):>6}ms")
    print(f"\n   Preload (one-time): {preload_ms}ms")

if __name__ == "__main__":
    asyncio.run(main())

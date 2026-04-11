"""
Parallel Analysis Node — SentiMind v5.1 Latency Optimization

Combines Cognitive Distortion (Node 4) and Trend Analyzer (Node 5) into a single
LangGraph node that runs both analyses concurrently via asyncio.gather.

WHY THIS WORKS:
  - Both nodes only READ from fused_emotion and fused_intensity (set by Node 3)
  - Neither node writes to any field the other reads
  - Both are independent: distortion scans keywords, trend queries DB
  - Running them in parallel saves ~50-300ms per message

BEFORE (sequential):
  emotion_fusion → cognitive_distortion → trend_analyzer  (~360ms total)

AFTER (parallel):
  emotion_fusion → parallel_analysis  (~310ms total, saves ~50ms best case)
                   ├─ cognitive_distortion  (~10-300ms)
                   └─ trend_analyzer        (~50ms)

Output: merged dict of both nodes' state updates.
"""

import asyncio
from ..agent.state import MentalHealthState
from .cognitive_distortion_node import cognitive_distortion_node
from .trend_analyzer_node import trend_analyzer_node


async def parallel_analysis_node(state: MentalHealthState) -> dict:
    """
    Run cognitive distortion detection and trend analysis in parallel.
    
    Both nodes are read-only consumers of fused_emotion/fused_intensity
    with no inter-dependency, making them safe to parallelize.
    
    Returns: merged dict of both nodes' outputs.
    """
    print("\n[NODE: PARALLEL] ⚡ Running distortion + trend analysis concurrently...")

    # Run both nodes concurrently
    distortion_result, trend_result = await asyncio.gather(
        cognitive_distortion_node(state),
        trend_analyzer_node(state),
        return_exceptions=True,
    )

    # Handle potential exceptions gracefully
    merged = {}

    if isinstance(distortion_result, Exception):
        print(f"[NODE: PARALLEL] ⚠️ Distortion node failed: {str(distortion_result)[:100]}")
        merged.update({
            "distortion_type": None,
            "distortion_confidence": 0.0,
            "distortion_explanation": None,
            "all_distortions": [],
        })
    else:
        merged.update(distortion_result)

    if isinstance(trend_result, Exception):
        print(f"[NODE: PARALLEL] ⚠️ Trend node failed: {str(trend_result)[:100]}")
        merged.update({
            "emotional_trend": "stable",
            "trend_window": [],
        })
    else:
        merged.update(trend_result)

    print(f"[NODE: PARALLEL] ✅ Parallel analysis complete | "
          f"Distortion: {merged.get('distortion_type', 'none')} | "
          f"Trend: {merged.get('emotional_trend', 'stable')}")

    return merged

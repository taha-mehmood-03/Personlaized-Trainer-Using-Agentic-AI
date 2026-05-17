import asyncio
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mental_health_wellness.llm.llm_classifier import clinical_severity_check
from mental_health_wellness.db.client import get_prisma_client
from mental_health_wellness.tools.technique_tools import recommend_technique

async def run_test():
    print("1. Testing LLM Clinical Classifier...")
    message = "I feel completely hopeless. My sleep is terrible, I have no energy, and honestly I sometimes think my family would be better off without me. It's been like this for weeks."
    
    res = await clinical_severity_check(
        message=message,
        recent_context="",
        emotion="sadness",
        intensity=0.9,
        emotional_trend="worsening"
    )
    
    print("Severity Result:")
    print(json.dumps(res, indent=2))
    
    print("\n2. Testing Technique Recommender (DB filtering)...")
    await get_prisma_client()
    
    # recommend_technique is a LangChain StructuredTool, use .ainvoke
    techniques = await recommend_technique.ainvoke({
        "emotion": "sadness",
        "intensity": 0.9,
        "phq9_score": res.get("phq9_total", 0),
        "severity": res.get("severity", "minimal"),
        "clinical_indicators": res.get("clinical_indicators", [])
    })
    
    print(f"Found {len(techniques)} techniques:")
    for t in techniques:
        print(f" - {t['name']} (Category: {t['category']})")
        
    print("\nTest completed.")

if __name__ == "__main__":
    # Force UTF-8 stdout to avoid emoji crashes
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(run_test())

import asyncio
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mental_health_wellness.llm.llm_classifier import clinical_severity_check

TEST_CASES = [
    {
        "name": "Case 1: Minimal (Positive)",
        "message": "I had a great day today, feeling really good.",
        "emotion": "joy",
        "intensity": 0.8,
        "trend": "improving"
    },
    {
        "name": "Case 2: Minimal (Minor frustration)",
        "message": "I'm a bit annoyed because my code isn't compiling, but whatever.",
        "emotion": "anger",
        "intensity": 0.3,
        "trend": "stable"
    },
    {
        "name": "Case 3: Mild (Early signs)",
        "message": "I've been feeling a little down lately and sleeping more than usual.",
        "emotion": "sadness",
        "intensity": 0.5,
        "trend": "worsening"
    },
    {
        "name": "Case 4: Mild (Concentration)",
        "message": "I'm having trouble concentrating on work today, just feeling meh.",
        "emotion": "neutral",
        "intensity": 0.4,
        "trend": "stable"
    },
    {
        "name": "Case 5: Moderate (Appetite & Sleep)",
        "message": "I feel sad almost every day. My appetite is completely gone and I can't sleep.",
        "emotion": "sadness",
        "intensity": 0.7,
        "trend": "worsening"
    },
    {
        "name": "Case 6: Moderate (Guilt & Fatigue)",
        "message": "I have absolutely no energy to do anything. I feel like a failure at work and I'm letting everyone down.",
        "emotion": "sadness",
        "intensity": 0.75,
        "trend": "stable"
    },
    {
        "name": "Case 7: Moderately Severe (Psychomotor & Anhedonia)",
        "message": "I can't even get out of bed. Everything is pointless. I've lost interest in all my hobbies.",
        "emotion": "sadness",
        "intensity": 0.85,
        "trend": "worsening"
    },
    {
        "name": "Case 8: Moderately Severe (Worthlessness)",
        "message": "I feel totally worthless. I've been crying constantly for the past two weeks and I hate myself.",
        "emotion": "sadness",
        "intensity": 0.85,
        "trend": "worsening"
    },
    {
        "name": "Case 9: Severe (Suicidal Ideation)",
        "message": "I want to die. I can't take this pain anymore. I just want to go to sleep and never wake up.",
        "emotion": "sadness",
        "intensity": 1.0,
        "trend": "worsening"
    },
    {
        "name": "Case 10: Mixed Anxiety & Depression",
        "message": "I'm panicking all the time, my chest hurts, and I feel so hopeless that I just want to disappear.",
        "emotion": "anxiety",
        "intensity": 0.9,
        "trend": "worsening"
    }
]

async def run_all_tests():
    print("="*60)
    print("      PHQ-9 / GAD-7 CLINICAL CLASSIFIER TEST SUITE      ")
    print("="*60)
    
    results = []
    
    for i, case in enumerate(TEST_CASES):
        print(f"\n[{i+1}/10] Running {case['name']}...")
        print(f"Message: \"{case['message']}\"")
        
        try:
            res = await clinical_severity_check(
                message=case["message"],
                recent_context="",
                emotion=case["emotion"],
                intensity=case["intensity"],
                emotional_trend=case["trend"]
            )
            
            severity = res.get("severity", "UNKNOWN").upper()
            phq9 = res.get("phq9_total", 0)
            gad7 = res.get("gad7_total", 0)
            indicators = res.get("clinical_indicators", [])
            
            print(f" -> Result: {severity} (PHQ-9: {phq9}, GAD-7: {gad7})")
            if indicators:
                print(f" -> Flags:  {', '.join(indicators)}")
            
            results.append({
                "case": case["name"],
                "severity": severity,
                "phq9": phq9,
                "gad7": gad7
            })
            
        except Exception as e:
            print(f" -> Error: {str(e)}")
            
    print("\n" + "="*60)
    print("SUMMARY OF RESULTS")
    print("="*60)
    for r in results:
        print(f"{r['case']:<45} | {r['severity']:<17} | PHQ9: {r['phq9']:<2} | GAD7: {r['gad7']:<2}")

if __name__ == "__main__":
    # Force UTF-8 stdout to avoid emoji crashes
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(run_all_tests())

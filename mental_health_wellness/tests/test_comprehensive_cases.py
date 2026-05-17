import asyncio
import sys
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mental_health_wellness.llm.llm_classifier import clinical_severity_check
from mental_health_wellness.db.client import get_prisma_client
from mental_health_wellness.tools.technique_tools import recommend_technique

TEST_CASES = [
    {
        "name": "Case_1_Healthy",
        "message": "Things are going pretty well. I'm just here to learn some basic mindfulness to stay focused at work.",
        "emotion": "neutral",
        "intensity": 0.2,
        "trend": "stable"
    },
    {
        "name": "Case_2_Mild_Stress",
        "message": "I'm feeling a bit overwhelmed with my exams coming up. I haven't been sleeping great but it's manageable.",
        "emotion": "anxiety",
        "intensity": 0.5,
        "trend": "worsening"
    },
    {
        "name": "Case_3_Moderate_Depression",
        "message": "I've been feeling really down for the last two weeks. I just sit on the couch and stare at the wall. My appetite is completely gone.",
        "emotion": "sadness",
        "intensity": 0.7,
        "trend": "worsening"
    },
    {
        "name": "Case_4_Severe_Anhedonia",
        "message": "Nothing brings me joy anymore. Even playing with my kids feels like a massive chore. I'm so exhausted I can barely function.",
        "emotion": "sadness",
        "intensity": 0.85,
        "trend": "worsening"
    },
    {
        "name": "Case_5_Suicidal_Ideation",
        "message": "I can't take this pain anymore. Everyone would be better off if I was just gone. I think about ending it every night.",
        "emotion": "sadness",
        "intensity": 1.0,
        "trend": "worsening"
    },
    {
        "name": "Case_6_Severe_Panic",
        "message": "My heart is racing, I can't breathe, I feel like I'm going to die right now! Please help me!",
        "emotion": "fear",
        "intensity": 0.95,
        "trend": "worsening"
    },
    {
        "name": "Case_7_Agitated_Anger",
        "message": "I am so furiously angry at my boss I could scream. He completely humiliated me today and I can't stop shaking.",
        "emotion": "anger",
        "intensity": 0.9,
        "trend": "worsening"
    },
    {
        "name": "Case_8_Chronic_Guilt",
        "message": "I'm a terrible person. I always let everyone down. I've felt this worthless since I was a teenager.",
        "emotion": "sadness",
        "intensity": 0.8,
        "trend": "stable"
    },
    {
        "name": "Case_9_Positive_Rebound",
        "message": "I actually used that breathing exercise you taught me yesterday and I slept through the night for the first time in weeks!",
        "emotion": "joy",
        "intensity": 0.8,
        "trend": "improving"
    },
    {
        "name": "Case_10_Mixed_Symptoms",
        "message": "I'm so anxious about losing my job that I've stopped eating, and I'm so depressed about it that I can't get out of bed to even try looking for a new one.",
        "emotion": "fear",
        "intensity": 0.85,
        "trend": "worsening"
    }
]

async def run_all_tests():
    # Ensure results directory exists
    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(exist_ok=True)
    
    # Initialize DB client once
    await get_prisma_client()
    
    print(f"Running {len(TEST_CASES)} comprehensive test cases...\n")
    
    for i, case in enumerate(TEST_CASES):
        filename = output_dir / f"{i+1:02d}_{case['name']}.txt"
        print(f"Executing {case['name']} -> saving to {filename}")
        
        try:
            # 1. Run Clinical Classifier
            res = await clinical_severity_check(
                message=case["message"],
                recent_context="",
                emotion=case["emotion"],
                intensity=case["intensity"],
                emotional_trend=case["trend"]
            )
            
            severity = res.get("severity", "minimal").upper()
            phq9 = res.get("phq9_total", 0)
            gad7 = res.get("gad7_total", 0)
            indicators = res.get("clinical_indicators", [])
            classifier_reasoning = res.get("reasoning", "No reasoning provided.")
            
            # 2. Get Recommendations from DB
            techniques = await recommend_technique.ainvoke({
                "emotion": case["emotion"],
                "intensity": case["intensity"],
                "phq9_score": phq9,
                "severity": severity.lower(),
                "clinical_indicators": indicators
            })
            
            # 3. Write detailed report
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"TEST CASE: {case['name']}\n")
                f.write("="*60 + "\n")
                f.write(f"INPUT MESSAGE: \"{case['message']}\"\n")
                f.write(f"BASE EMOTION:  {case['emotion'].upper()} (Intensity: {case['intensity']})\n")
                f.write("="*60 + "\n\n")
                
                f.write("1. CLINICAL SEVERITY ANALYSIS (LLM)\n")
                f.write("-" * 40 + "\n")
                f.write(f"Detected Severity:   {severity}\n")
                f.write(f"Estimated PHQ-9:     {phq9} / 27\n")
                f.write(f"Estimated GAD-7:     {gad7} / 21\n")
                f.write(f"Clinical Indicators: {', '.join(indicators) if indicators else 'None detected'}\n")
                f.write(f"Confidence Score:    {res.get('confidence', 0.0):.0%}\n\n")
                f.write(f"LLM Reasoning:\n{classifier_reasoning}\n\n\n")
                
                f.write("2. TECHNIQUE SELECTION (DATABASE GATING)\n")
                f.write("-" * 40 + "\n")
                
                # Logic explanation string
                reasoning = []
                reasoning.append(f"- Matched Target Emotion: {case['emotion'].upper()}")
                if severity != "MINIMAL":
                    reasoning.append(f"- Applied Clinical Bounds: minPhq9 <= {phq9} AND maxPhq9 >= {phq9}")
                    reasoning.append(f"- Safety Requirement: Must be marked SafeAtSeverity={severity}")
                if indicators:
                    reasoning.append(f"- Contraindication Filter: Excluded techniques matching flags {indicators}")
                
                f.write("Filtering Rules Applied:\n")
                f.write("\n".join(reasoning) + "\n\n")
                
                f.write(f"Recommended Exercises (Top {len(techniques)}):\n")
                if not techniques:
                    f.write("  [!] CRITICAL: No safe techniques found for this profile.\n")
                else:
                    for t in techniques:
                        f.write(f"  > {t['name']} (Category: {t['category']})\n")
                        f.write(f"    Difficulty: {t['difficulty']}, Duration: {t['duration_minutes']}m\n")
                        f.write(f"    Why: {t['why_it_works']}\n\n")
                        
        except Exception as e:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"ERROR executing test {case['name']}:\n{str(e)}\n")
            print(f"  -> Error occurred (saved to file)")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(run_all_tests())

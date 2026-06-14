"""
Seed New 60 Techniques - With Proper Emotion Mapping
"""

import asyncio
from prisma import Prisma
from datetime import datetime
import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mental_health_wellness.techniques.emotion_metadata import (  # noqa: E402
    annotate_technique_dict,
    prisma_metadata_fields,
    target_emotions_for_technique,
)

# ============================================
# EMOTION MAPPING TO PRISMA ENUM
# ============================================

EMOTION_MAP = {
    "anxiety": "ANXIETY",
    "sadness": "SADNESS",
    "anger": "ANGER",
    "fear": "FEAR",
    "joy": "JOY",
    "neutral": "NEUTRAL",
    "disgust": "DISGUST",
    "surprise": "SURPRISE",
    # Legacy mappings
    "fatigue": "SADNESS",
    "depression": "SADNESS",
    "low_energy": "SADNESS",
    "inflammation": "SADNESS",
    "panic": "ANXIETY",
    "hyperventilation": "ANXIETY",
    "asthma": "ANXIETY",
    "sleep_issues": "SADNESS",
    "overheating": "ANGER",
    "frustration": "ANGER",
    "irritability": "ANGER",
    "distraction": "ANXIETY",
    "restlessness": "ANXIETY",
    "cold": "SADNESS",
    "lack_of_focus": "ANXIETY",
    "overwhelm": "ANXIETY",
    "stress": "ANXIETY",
    "creative_block": "SADNESS",
    "burnout": "SADNESS",
    "low_mood": "SADNESS",
    "negativity": "SADNESS",
    "racing_thoughts": "ANXIETY",
    "mood_swings": "ANXIETY",
    "bipolar": "ANXIETY",
    "procrastination": "ANXIETY",
    "avoidance": "ANXIETY",
    "hopelessness": "SADNESS",
    "low_expectancy": "SADNESS",
    "self_criticism": "SADNESS",
    "shame": "SADNESS",
    "guilt": "SADNESS",
    "resentment": "ANGER",
    "bitterness": "ANGER",
    "grief": "SADNESS",
    "unresolved_feelings": "ANGER",
    "impulsivity": "ANGER",
    "urges": "ANGER",
    "addiction": "ANGER",
    "confusion": "ANXIETY",
    "ambivalence": "ANXIETY",
    "indecision": "ANXIETY",
    "anhedonia": "SADNESS",
    "isolation": "SADNESS",
    "social_anxiety": "ANXIETY",
    "phobias": "ANXIETY",
    "generalized_anxiety": "ANXIETY",
    "worry": "ANXIETY",
}

def normalize_target_emotions(emotions: list) -> list:
    """Convert emotions to Prisma enum values"""
    normalized = []
    for emotion in emotions:
        if isinstance(emotion, str):
            emotion_lower = emotion.lower().replace(" ", "_").replace("-", "_")
            if emotion_lower in EMOTION_MAP:
                norm_emotion = EMOTION_MAP[emotion_lower]
            else:
                norm_emotion = emotion.upper()
            
            if norm_emotion not in normalized:
                normalized.append(norm_emotion)
    return normalized if normalized else ["NEUTRAL"]


# Import techniques from the sibling seed_new_techniques.py file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from seed_new_techniques import (
        advanced_breathing_techniques,
        advanced_mindfulness_techniques,
        advanced_cbt_techniques,
        advanced_dbt_techniques,
        advanced_journaling_techniques,
        advanced_behavioral_techniques
    )
except ImportError:
    print("Error: Could not import techniques from seed_new_techniques.py")
    print("Make sure seed_new_techniques.py is in the current directory")
    sys.exit(1)


async def seed_new_techniques():
    """Seed the new 60 techniques"""
    prisma = Prisma()
    await prisma.connect()
    
    print("\n" + "="*70)
    print("  SEEDING NEW TECHNIQUES (60 total)")
    print("="*70)
    
    # Get or create categories
    categories = {}
    category_names = ["Breathing", "Mindfulness", "CBT", "DBT", "Journaling", "Behavioral Activation"]
    
    for cat_name in category_names:
        cat = await prisma.techniquecategory.find_first(where={"name": cat_name})
        if cat:
            categories[cat_name] = cat.id
            print(f"  [OK] Category exists: {cat_name}")
        else:
            print(f"  [!] Category not found: {cat_name}")
    
    if not categories:
        print("[ERROR] No categories found!")
        await prisma.disconnect()
        return
    
    # Collect all techniques
    all_new_techniques = [
        (advanced_breathing_techniques, "Breathing"),
        (advanced_mindfulness_techniques, "Mindfulness"),
        (advanced_cbt_techniques, "CBT"),
        (advanced_dbt_techniques, "DBT"),
        (advanced_journaling_techniques, "Journaling"),
        (advanced_behavioral_techniques, "Behavioral Activation"),
    ]
    
    total_inserted = 0
    total_existing = 0
    
    print("\n" + "-"*70)
    
    for techniques_list, category_name in all_new_techniques:
        if not categories.get(category_name):
            print(f"  [!] Skipping {category_name} - category not found")
            continue
        
        cat_id = categories[category_name]
        print(f"\n  [{category_name.upper()}] ({len(techniques_list)} techniques)")
        
        for tech_data in techniques_list:
            annotate_technique_dict(tech_data, category_name)
            metadata_fields = prisma_metadata_fields(tech_data, category_name)

            # Check if already exists
            existing = await prisma.technique.find_first(
                where={"name": tech_data["name"]}
            )
            
            if existing:
                total_existing += 1
                await prisma.technique.update(
                    where={"id": existing.id},
                    data={
                        "targetEmotions": normalize_target_emotions(target_emotions_for_technique(tech_data, category_name)),
                        **metadata_fields,
                    },
                )
                print(f"    [OK] {tech_data['name']}")
                continue
            
            # Prepare data with proper emotion mapping
            create_data = {
                "categoryId": cat_id,
                "name": tech_data["name"],
                "brief": tech_data["brief"],
                "description": tech_data["description"],
                "steps": tech_data["steps"],
                "durationMinutes": tech_data["duration_minutes"],
                "difficulty": tech_data["difficulty"],
                "targetEmotions": normalize_target_emotions(target_emotions_for_technique(tech_data, category_name)),
                "whyItWorks": tech_data.get("why_it_works", ""),
                "effectiveness": tech_data.get("effectiveness", 0.8),
                "isActive": True,
                **metadata_fields,
            }
            
            try:
                await prisma.technique.create(data=create_data)
                total_inserted += 1
                print(f"    [+] {tech_data['name']}")
            except Exception as e:
                print(f"    [ERROR] {tech_data['name']} - Error: {str(e)[:60]}")
    
    # Summary
    print("\n" + "="*70)
    print("  SEEDING COMPLETE")
    print("="*70)
    print(f"  Inserted: {total_inserted} new techniques")
    print(f"  Already existed: {total_existing} techniques")
    print(f"  Total new: {total_inserted + total_existing}")
    print("="*70)
    
    await prisma.disconnect()


if __name__ == "__main__":
    asyncio.run(seed_new_techniques())

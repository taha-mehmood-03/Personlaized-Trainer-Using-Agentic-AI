"""
Enhanced Seed Script - Populate database with comprehensive technique data
Categories: Breathing, Mindfulness, CBT, DBT, Journaling, Behavioral Activation
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
    "surprise": "SURPRISE"
}

def normalize_target_emotions(emotions: list) -> list:
    """Convert lowercase emotions to Prisma enum values"""
    normalized = []
    for emotion in emotions:
        if isinstance(emotion, str):
            emotion_lower = emotion.lower()
            # Handle mapped emotions
            if emotion_lower in EMOTION_MAP:
                normalized.append(EMOTION_MAP[emotion_lower])
            else:
                # If not in map, try direct uppercase conversion
                normalized.append(emotion.upper())
    return normalized


async def seed_techniques():
    """Seed the database with comprehensive techniques"""
    prisma = Prisma()
    await prisma.connect()
    
    print("\n" + "="*70)
    print("  ENHANCED TECHNIQUE SEEDING")
    print("="*70)
    print("[SEED] Starting technique seeding...")
    
    # ============================================
    # CATEGORIES
    # ============================================
    
    categories_data = [
        {"name": "Breathing", "description": "Breathing exercises to calm the nervous system", "icon": "🌬️"},
        {"name": "Mindfulness", "description": "Present-moment awareness practices", "icon": "🧘"},
        {"name": "CBT", "description": "Cognitive Behavioral Therapy techniques", "icon": "🧠"},
        {"name": "DBT", "description": "Dialectical Behavior Therapy skills", "icon": "⚖️"},
        {"name": "Journaling", "description": "Writing-based therapeutic exercises", "icon": "📝"},
        {"name": "Behavioral Activation", "description": "Activity-based mood improvement", "icon": "🏃"},
    ]
    
    categories = {}
    for cat_data in categories_data:
        existing = await prisma.techniquecategory.find_first(
            where={"name": cat_data["name"]}
        )
        if existing:
            cat = existing
            print(f"  [✓] Category exists: {cat.name}")
        else:
            cat = await prisma.techniquecategory.create(data=cat_data)
            print(f"  [✨] Created category: {cat.name}")
        categories[cat.name] = cat.id
    
    print("\n" + "-"*70)
    
    # ============================================
    # TECHNIQUES BY CATEGORY
    # ============================================
    
    all_techniques = []
    
    # ----------------------------------------------------------------------
    # CATEGORY 1: BREATHING TECHNIQUES (8 techniques)
    # ----------------------------------------------------------------------
    
    breathing_techniques = [
        {
            "name": "4-7-8 Breathing",
            "brief": "Inhale for 4, hold for 7, exhale for 8 counts",
            "description": "A calming breathing technique that activates the parasympathetic nervous system. Also known as the 'relaxing breath,' this technique helps reduce anxiety, manage stress, and fall asleep faster.",
            "steps": [
                "Find a comfortable seated position with your back straight",
                "Place the tip of your tongue against the ridge behind your upper front teeth",
                "Exhale completely through your mouth, making a whoosh sound",
                "Close your mouth and inhale quietly through your nose for 4 counts",
                "Hold your breath for 7 counts",
                "Exhale completely through your mouth for 8 counts, making a whoosh sound",
                "Repeat this cycle 4-8 times"
            ],
            "duration_minutes": 5,
            "difficulty": "EASY",
            "target_emotions": ["anxiety", "anger"],
            "why_it_works": "Extending the exhale activates the parasympathetic nervous system, lowering heart rate and blood pressure. The specific counts maximize oxygen-carbon dioxide exchange and focus the mind.",
            "effectiveness": 0.87,
            "scientific_background": "Based on pranayama (yogic breathing) and validated in studies for reducing physiological arousal."
        },
        {
            "name": "Box Breathing",
            "brief": "Equal breathing pattern - inhale, hold, exhale, hold",
            "description": "Also known as square breathing, this technique involves equal counts for each phase of breath. Used by Navy SEALs and first responders to stay calm under pressure.",
            "steps": [
                "Sit comfortably with feet flat on the floor and hands resting in your lap",
                "Inhale slowly through your nose for 4 counts",
                "Hold your breath for 4 counts",
                "Exhale slowly through your mouth for 4 counts",
                "Hold your lungs empty for 4 counts",
                "Repeat for 5-10 cycles"
            ],
            "duration_minutes": 5,
            "difficulty": "EASY",
            "target_emotions": ["anxiety"],
            "why_it_works": "The equal pattern creates rhythm and predictability, which signals safety to the nervous system. The holds between breaths increase CO2 tolerance, which has a calming effect.",
            "effectiveness": 0.85,
            "scientific_background": "Used in high-stress professions; research shows it reduces cortisol and improves HRV."
        },
        {
            "name": "Belly Breathing",
            "brief": "Diaphragmatic breathing for deep relaxation",
            "description": "Also called diaphragmatic breathing, this technique engages the diaphragm fully, promoting the relaxation response and reducing the fight-or-flight response.",
            "steps": [
                "Lie on your back with knees bent or sit comfortably",
                "Place one hand on your chest and the other on your belly",
                "Inhale slowly through your nose for 4 seconds",
                "Feel your belly rise (the hand on your chest should stay relatively still)",
                "Exhale slowly through pursed lips for 6-8 seconds",
                "Feel your belly fall as you exhale completely",
                "Repeat for 5-10 minutes"
            ],
            "duration_minutes": 8,
            "difficulty": "EASY",
            "target_emotions": ["anxiety", "anger"],
            "why_it_works": "Diaphragmatic breathing stimulates the vagus nerve, which activates the parasympathetic nervous system. This lowers heart rate, blood pressure, and stress hormones.",
            "effectiveness": 0.88,
            "scientific_background": "Extensively studied for anxiety disorders, COPD, and stress reduction. Increases HRV and reduces cortisol."
        },
        {
            "name": "Alternate Nostril Breathing",
            "brief": "Nadi Shodhana - balance the nervous system",
            "description": "An ancient yogic breathing technique that balances the left and right hemispheres of the brain, creating mental clarity and calm.",
            "steps": [
                "Sit comfortably with spine straight",
                "Use your right thumb to close your right nostril",
                "Inhale slowly through your left nostril for 4 counts",
                "Close your left nostril with your ring finger, release thumb",
                "Exhale through your right nostril for 4 counts",
                "Inhale through right nostril for 4 counts",
                "Close right nostril, release left, exhale left for 4 counts",
                "This completes one cycle. Repeat 5-10 times"
            ],
            "duration_minutes": 8,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety", "sadness"],
            "why_it_works": "Balances the autonomic nervous system, synchronizes brain hemispheres, and clears energetic channels. Particularly effective for racing thoughts.",
            "effectiveness": 0.82,
            "scientific_background": "Studies show improved cardiovascular function and reduced perceived stress."
        },
        {
            "name": "Resonance Breathing",
            "brief": "Breathing at 5-6 breaths per minute for optimal HRV",
            "description": "Breathing at your resonant frequency (typically 5-6 breaths per minute) maximizes heart rate variability and baroreflex sensitivity, creating deep physiological calm.",
            "steps": [
                "Sit comfortably with eyes closed",
                "Inhale slowly for 5-6 seconds",
                "Exhale slowly for 5-6 seconds (target 5-6 total breaths per minute)",
                "Use a timer or app if available to maintain rhythm",
                "Continue for 10-20 minutes",
                "Focus on the sensation of air moving in and out"
            ],
            "duration_minutes": 15,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety"],
            "why_it_works": "Breathing at resonant frequency creates a positive feedback loop between heart rate, blood pressure, and breathing centers, maximizing heart rate variability - a marker of resilience.",
            "effectiveness": 0.90,
            "scientific_background": "Extensively researched by HeartMath Institute; shown to increase HRV, reduce PTSD symptoms, and improve emotional regulation."
        },
        {
            "name": "Pursed Lip Breathing",
            "brief": "Slow, controlled exhalation through pursed lips",
            "description": "A simple technique that slows breathing rate and keeps airways open longer, particularly helpful when feeling short of breath or panicked.",
            "steps": [
                "Relax your neck and shoulder muscles",
                "Inhale slowly through your nose for 2 counts",
                "Pucker your lips as if you're going to whistle",
                "Exhale slowly and gently through pursed lips for 4 counts",
                "Do not force the air out; let it escape naturally",
                "Repeat for several minutes until you feel calmer"
            ],
            "duration_minutes": 5,
            "difficulty": "EASY",
            "target_emotions": ["anxiety"],
            "why_it_works": "Creates back-pressure in airways, keeping them open longer and improving oxygen exchange. The longer exhale activates the relaxation response.",
            "effectiveness": 0.83,
            "scientific_background": "Commonly taught in pulmonary rehabilitation; effective for panic attacks and COPD."
        },
        {
            "name": "Breath Counting",
            "brief": "Count breaths to anchor attention",
            "description": "A Zen meditation technique that uses counting to anchor attention and prevent mind-wandering during breathing practice.",
            "steps": [
                "Sit comfortably with eyes partially closed",
                "Breathe naturally without trying to change it",
                "On the exhale, silently count 'one'",
                "Next exhale, count 'two'",
                "Continue up to ten, then start over",
                "If you lose count, gently return to one",
                "Notice when your mind wanders without judgment"
            ],
            "duration_minutes": 10,
            "difficulty": "EASY",
            "target_emotions": ["anxiety", "sadness"],
            "why_it_works": "Gives the mind a simple task, preventing rumination and worry. The gentle focus reduces default mode network activity.",
            "effectiveness": 0.79,
            "scientific_background": "Traditional Zen practice; modern research shows it reduces mind-wandering and improves attention."
        },
        {
            "name": "3-Part Breath",
            "brief": "Dirga Pranayama - fill three parts of the torso",
            "description": "A yogic breathing practice that brings awareness and expansion to the abdomen, rib cage, and upper chest, creating full oxygen exchange.",
            "steps": [
                "Lie on your back or sit comfortably",
                "Place one hand on belly, one on chest",
                "Inhale into the lower belly (hand rises)",
                "Continue inhaling as ribs expand (hand moves outward)",
                "Fill upper chest (hand on chest rises)",
                "Exhale slowly from upper chest, ribs, then belly",
                "Repeat 10-20 breaths"
            ],
            "duration_minutes": 8,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety"],
            "why_it_works": "Encourages full diaphragmatic breathing, increases lung capacity, and brings awareness to the whole breathing process, reducing tension patterns.",
            "effectiveness": 0.84,
            "scientific_background": "Based on yogic pranayama; improves respiratory function and reduces anxiety."
        }
    ]
    
    for tech in breathing_techniques:
        tech["categoryId"] = categories["Breathing"]
        all_techniques.append(tech)
    
    # ----------------------------------------------------------------------
    # CATEGORY 2: MINDFULNESS TECHNIQUES (8 techniques)
    # ----------------------------------------------------------------------
    
    mindfulness_techniques = [
        {
            "name": "5-4-3-2-1 Grounding",
            "brief": "Sensory awareness to anchor in the present",
            "description": "A powerful grounding technique that uses your five senses to anchor you in the present moment, especially helpful during anxiety, panic, or dissociation.",
            "steps": [
                "Find a comfortable position and take 3 deep breaths",
                "ACKNOWLEDGE 5 things you SEE around you",
                "ACKNOWLEDGE 4 things you can TOUCH (feel of fabric, ground under feet)",
                "ACKNOWLEDGE 3 things you HEAR (external sounds, not internal thoughts)",
                "ACKNOWLEDGE 2 things you can SMELL (or 2 favorite smells)",
                "ACKNOWLEDGE 1 thing you can TASTE (or a sip of water)",
                "Take a final deep breath and notice how you feel"
            ],
            "duration_minutes": 5,
            "difficulty": "EASY",
            "target_emotions": ["anxiety", "sadness"],
            "why_it_works": "Forces attention outward and away from internal distress. Engaging multiple senses interrupts the anxiety cycle and activates the prefrontal cortex, reducing amygdala reactivity.",
            "effectiveness": 0.89,
            "scientific_background": "Widely used in DBT and trauma therapy; research shows sensory grounding reduces panic symptoms and dissociative episodes."
        },
        {
            "name": "Body Scan Meditation",
            "brief": "Progressive attention through body parts",
            "description": "A foundational mindfulness practice that involves systematically bringing attention to different parts of the body, noticing sensations without judgment.",
            "steps": [
                "Lie down or sit comfortably with eyes closed",
                "Take 3 deep breaths to center yourself",
                "Bring awareness to the top of your head",
                "Slowly move attention down: face, neck, shoulders",
                "Continue through arms, chest, back, abdomen",
                "Move through hips, legs, feet, toes",
                "Notice any sensations without trying to change them",
                "When you reach your toes, take a few deep breaths",
                "Gently wiggle fingers and toes, open eyes"
            ],
            "duration_minutes": 15,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety", "sadness"],
            "why_it_works": "Develops interoceptive awareness (ability to sense internal body states) and reduces rumination by shifting focus from thoughts to physical sensations.",
            "effectiveness": 0.86,
            "scientific_background": "Extensively researched in MBSR (Mindfulness-Based Stress Reduction); shown to reduce pain, anxiety, and depression."
        },
        {
            "name": "Mindful Walking",
            "brief": "Walking meditation to ground in movement",
            "description": "A moving meditation that brings mindfulness into physical activity, perfect for those who struggle with sitting meditation or want to integrate mindfulness into daily life.",
            "steps": [
                "Find a quiet path (20-30 steps long)",
                "Stand still and take 3 conscious breaths",
                "Begin walking slowly, much slower than normal",
                "Notice the sensation of your foot lifting",
                "Feel your foot moving through the air",
                "Notice the heel touching down, then the rest of the foot",
                "Feel the weight shift from back foot to front foot",
                "Continue for 10-15 minutes, maintaining awareness"
            ],
            "duration_minutes": 15,
            "difficulty": "EASY",
            "target_emotions": ["anxiety", "sadness"],
            "why_it_works": "Combines physical activity with mindfulness, reducing cortisol while increasing focus. The rhythmic nature is naturally calming.",
            "effectiveness": 0.82,
            "scientific_background": "Traditional Buddhist practice; studies show it reduces depression and improves well-being."
        },
        {
            "name": "RAIN Meditation",
            "brief": "Recognize, Allow, Investigate, Nurture",
            "description": "A 4-step mindfulness practice for working with difficult emotions with compassion and clarity, developed by meditation teacher Michele McDonald.",
            "steps": [
                "RECOGNIZE: Notice and name what you're feeling",
                "ALLOW: Let the feeling be there without trying to fix it",
                "INVESTIGATE: With curiosity, explore the sensation in your body",
                "NURTURE: Offer yourself kindness - place hand on heart, say something caring",
                "Take a few deep breaths",
                "Notice if anything has shifted"
            ],
            "duration_minutes": 10,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety", "sadness", "anger"],
            "why_it_works": "Combines mindfulness with self-compassion, allowing full processing of emotions without getting caught in them. The structured approach prevents overwhelm.",
            "effectiveness": 0.87,
            "scientific_background": "Integrated into trauma-informed mindfulness; research shows self-compassion practices reduce depression and anxiety."
        },
        {
            "name": "Mindful Eating",
            "brief": "Full attention to the experience of eating",
            "description": "A practice of bringing full awareness to the experience of eating, which can transform relationship with food and reduce stress around meals.",
            "steps": [
                "Choose a small piece of food (raisin, chocolate, fruit)",
                "Look at it as if you've never seen it before",
                "Notice colors, textures, light reflections",
                "Bring it to your nose, smell it deeply",
                "Place it in your mouth but don't chew yet",
                "Notice the sensation on your tongue",
                "Chew slowly, noticing taste and texture changes",
                "Notice the impulse to swallow before swallowing",
                "Follow the sensation of swallowing"
            ],
            "duration_minutes": 10,
            "difficulty": "EASY",
            "target_emotions": ["anxiety"],
            "why_it_works": "Slows down automatic behavior, increases enjoyment, and improves interoceptive awareness. Helps distinguish physical hunger from emotional hunger.",
            "effectiveness": 0.81,
            "scientific_background": "Used in eating disorder treatment; studies show reduced binge eating and improved satiety signals."
        },
        {
            "name": "Loving-Kindness Meditation",
            "brief": "Cultivate compassion for self and others",
            "description": "A practice of directing well-wishes toward yourself and others, which builds positive emotions and reduces negative affect.",
            "steps": [
                "Sit comfortably with eyes closed",
                "Bring to mind someone who loves you unconditionally",
                "Silently repeat phrases: 'May you be happy. May you be healthy. May you be safe. May you live with ease.'",
                "Now direct these phrases to yourself",
                "Then to a neutral person (someone you see regularly)",
                "Then to someone difficult (start with minor difficulty)",
                "Finally to all beings everywhere"
            ],
            "duration_minutes": 15,
            "difficulty": "MODERATE",
            "target_emotions": ["sadness", "anger"],
            "why_it_works": "Activates brain regions associated with positive affect and social connection. Reduces self-criticism and builds resilience.",
            "effectiveness": 0.84,
            "scientific_background": "Extensively researched; shown to increase positive emotions, reduce migraines, and slow cellular aging."
        },
        {
            "name": "STOP Practice",
            "brief": "Stop, Take a breath, Observe, Proceed",
            "description": "A brief mindfulness practice that can be done anywhere, anytime to reset during a stressful day.",
            "steps": [
                "S: STOP what you're doing. Pause for a moment.",
                "T: TAKE a breath. One conscious breath, feeling the sensation.",
                "O: OBSERVE what's happening inside and around you",
                "P: PROCEED with one thing that supports you right now",
                "That's it - the whole practice takes 30-60 seconds",
                "Use it multiple times throughout the day"
            ],
            "duration_minutes": 1,
            "difficulty": "EASY",
            "target_emotions": ["anxiety", "anger"],
            "why_it_works": "Interrupts the autopilot stress response and creates a moment of choice rather than reaction. Even brief mindfulness reduces cortisol.",
            "effectiveness": 0.88,
            "scientific_background": "Developed by mindfulness teacher Elisha Goldstein; micro-practices shown to accumulate benefits throughout the day."
        },
        {
            "name": "Mindfulness of Thoughts",
            "brief": "Observe thoughts as mental events, not facts",
            "description": "A practice of watching thoughts come and go like clouds in the sky, reducing their power and helping you see them as temporary mental events.",
            "steps": [
                "Sit comfortably and close your eyes",
                "Imagine sitting by a stream, watching leaves float by",
                "Place each thought on a leaf and watch it float away",
                "Or imagine thoughts as clouds passing in the sky",
                "Notice thoughts without engaging or judging them",
                "When you get caught in a thought, gently return to watching",
                "Continue for 10-15 minutes"
            ],
            "duration_minutes": 12,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety", "sadness"],
            "why_it_works": "Creates metacognitive awareness (seeing thoughts as thoughts rather than reality), which reduces their emotional impact and breaks rumination cycles.",
            "effectiveness": 0.86,
            "scientific_background": "Core component of MBCT (Mindfulness-Based Cognitive Therapy); shown to prevent depression relapse."
        }
    ]
    
    for tech in mindfulness_techniques:
        tech["categoryId"] = categories["Mindfulness"]
        all_techniques.append(tech)
    
    # ----------------------------------------------------------------------
    # CATEGORY 3: CBT TECHNIQUES (8 techniques)
    # ----------------------------------------------------------------------
    
    cbt_techniques = [
        {
            "name": "Thought Record",
            "brief": "Capture and challenge negative automatic thoughts",
            "description": "A structured way to examine and challenge negative automatic thoughts by looking at evidence and creating more balanced alternatives.",
            "steps": [
                "Describe the situation that triggered the emotion",
                "Identify the automatic thought that came to mind",
                "Rate how strongly you believe this thought (0-100%)",
                "Identify the emotion(s) you felt and rate intensity (0-100%)",
                "List evidence that SUPPORTS the automatic thought",
                "List evidence that DOES NOT SUPPORT the thought",
                "Create a more balanced, realistic thought",
                "Re-rate belief in original thought and emotion intensity"
            ],
            "duration_minutes": 15,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety", "sadness", "anger"],
            "why_it_works": "Breaks the automatic connection between thought and emotion by introducing rational analysis. The written format creates distance from thoughts.",
            "effectiveness": 0.88,
            "scientific_background": "Core CBT tool developed by Aaron Beck; extensively researched and validated for anxiety and depression."
        },
        {
            "name": "Cognitive Restructuring",
            "brief": "Identify and challenge cognitive distortions",
            "description": "Learn to identify common thinking errors (cognitive distortions) and replace them with more realistic thoughts.",
            "steps": [
                "Write down the negative thought",
                "Identify which cognitive distortion(s) are present:",
                "  - All-or-nothing thinking: Seeing things in black and white",
                "  - Catastrophizing: Expecting the worst possible outcome",
                "  - Overgeneralization: Using 'always' or 'never'",
                "  - Mind reading: Assuming what others think",
                "  - Emotional reasoning: 'I feel it, therefore it's true'",
                "Challenge each distortion with evidence",
                "Write a more balanced thought"
            ],
            "duration_minutes": 15,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety", "sadness", "anger"],
            "why_it_works": "Helps recognize patterns of distorted thinking and replace them with evidence-based alternatives, reducing emotional reactivity.",
            "effectiveness": 0.87,
            "scientific_background": "Foundational CBT technique; meta-analyses show large effect sizes for mood disorders."
        },
        {
            "name": "Behavioral Experiment",
            "brief": "Test predictions against reality",
            "description": "Design experiments to test the accuracy of your negative predictions or beliefs by gathering real-world evidence.",
            "steps": [
                "Identify a specific negative prediction (e.g., 'If I speak up, everyone will laugh')",
                "Rate how strongly you believe it (0-100%)",
                "Design an experiment to test it (specific, measurable, achievable)",
                "Predict what will happen and how you'll react",
                "Conduct the experiment",
                "Record what actually happened",
                "Compare outcome to prediction",
                "Re-rate your belief in the original prediction"
            ],
            "duration_minutes": 30,
            "difficulty": "HARD",
            "target_emotions": ["anxiety"],
            "why_it_works": "Directly challenges beliefs with real-world evidence, which is more powerful than just thinking about them. Builds confidence through experience.",
            "effectiveness": 0.89,
            "scientific_background": "Key CBT technique for anxiety disorders; especially effective for social anxiety and panic."
        },
        {
            "name": "Worry Time",
            "brief": "Scheduled time to process worries constructively",
            "description": "Contain worry to a specific time each day, preventing it from taking over your whole day while still giving it space to be processed.",
            "steps": [
                "Choose a 15-20 minute 'worry time' daily (same time, same place)",
                "When worries arise during the day, write them down briefly",
                "Tell yourself: 'I'll think about this during worry time'",
                "During worry time, review your list",
                "For each worry, ask: 'Is this a real problem I can solve or a hypothetical?'",
                "For real problems, brainstorm one small action",
                "For hypotheticals, practice letting go or acceptance",
                "When time is up, stop worrying until tomorrow"
            ],
            "duration_minutes": 20,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety"],
            "why_it_works": "Contains worry to a specific time, reducing all-day rumination while still validating concerns. The scheduling reduces the urgency of worries.",
            "effectiveness": 0.84,
            "scientific_background": "CBT technique for GAD; research shows it reduces worry time and anxiety severity."
        },
        {
            "name": "Pie Chart Technique",
            "brief": "Visualize responsibility distribution",
            "description": "When taking too much blame for negative events, use a pie chart to visualize all the factors that contributed, reducing excessive self-blame.",
            "steps": [
                "Draw a large circle (the pie)",
                "Write the negative event or outcome at the top",
                "List all possible contributing factors (your actions, others' actions, circumstances, luck, etc.)",
                "Assign a percentage to each factor based on actual contribution",
                "Draw slices representing each percentage",
                "Notice how your slice of responsibility compares to others",
                "Create a more balanced perspective"
            ],
            "duration_minutes": 10,
            "difficulty": "EASY",
            "target_emotions": ["sadness"],
            "why_it_works": "Visual representation makes overgeneralized self-blame literally smaller. It externalizes the tendency to take too much responsibility.",
            "effectiveness": 0.81,
            "scientific_background": "CBT technique for depression; helps correct the cognitive distortion of personalization."
        },
        {
            "name": "Cost-Benefit Analysis",
            "brief": "Weigh pros and cons of thoughts and behaviors",
            "description": "Evaluate the advantages and disadvantages of holding certain beliefs or engaging in certain behaviors to motivate change.",
            "steps": [
                "Identify a belief or behavior you want to evaluate",
                "Draw a line down the middle of a page",
                "Label left side 'Advantages/Costs of changing/keeping' and right side 'Disadvantages/Benefits'",
                "List all pros and cons honestly",
                "Review the list objectively",
                "Ask: 'Is this belief/behavior helping me or hurting me?'",
                "Decide if you want to work on changing it"
            ],
            "duration_minutes": 15,
            "difficulty": "EASY",
            "target_emotions": ["anxiety"],
            "why_it_works": "Makes implicit costs and benefits explicit, reducing emotional decision-making and increasing motivation for change.",
            "effectiveness": 0.79,
            "scientific_background": "Used in CBT and motivational interviewing; helps resolve ambivalence."
        },
        {
            "name": "Activity Scheduling",
            "brief": "Plan activities to improve mood",
            "description": "Schedule specific activities throughout the day to increase engagement and positive experiences, breaking the cycle of avoidance and low mood.",
            "steps": [
                "Create an hourly schedule for the week",
                "List activities that might bring: pleasure, mastery, connection",
                "Rate expected pleasure/mastery (0-10) before",
                "Schedule at least one activity per day",
                "After each activity, rate actual pleasure/mastery",
                "Notice that actual ratings are often higher than expected",
                "Gradually increase activities"
            ],
            "duration_minutes": 20,
            "difficulty": "MODERATE",
            "target_emotions": ["sadness"],
            "why_it_works": "Breaks the depression cycle where low mood leads to inactivity, which worsens mood. Provides structure and increases positive reinforcement.",
            "effectiveness": 0.86,
            "scientific_background": "Core component of Behavioral Activation; as effective as medication for depression in some studies."
        },
        {
            "name": "The Triple Column Technique",
            "brief": "Challenge automatic thoughts with evidence",
            "description": "A simple three-column format to identify and challenge negative automatic thoughts developed by Dr. David Burns.",
            "steps": [
                "Draw three columns on a page",
                "Column 1: 'Automatic Thought' - write the negative thought",
                "Column 2: 'Cognitive Distortion' - identify the distortion type",
                "Column 3: 'Rational Response' - write a balanced response",
                "Rate belief in automatic thought before (0-100%)",
                "Rate belief after writing rational response",
                "Notice how your feelings shift"
            ],
            "duration_minutes": 10,
            "difficulty": "EASY",
            "target_emotions": ["anxiety", "sadness"],
            "why_it_works": "Simple structure makes cognitive restructuring accessible. The written format externalizes thoughts for objective examination.",
            "effectiveness": 0.85,
            "scientific_background": "Popularized in 'Feeling Good' by David Burns; millions have used it successfully."
        }
    ]
    
    for tech in cbt_techniques:
        tech["categoryId"] = categories["CBT"]
        all_techniques.append(tech)
    
    # ----------------------------------------------------------------------
    # CATEGORY 4: DBT TECHNIQUES (8 techniques)
    # ----------------------------------------------------------------------
    
    dbt_techniques = [
        {
            "name": "TIPP Skills",
            "brief": "Rapid distress tolerance: Temperature, Intense exercise, Paced breathing, Paired relaxation",
            "description": "A set of four skills designed to quickly change your body chemistry and reduce extreme emotional arousal. Use when emotions are overwhelming.",
            "steps": [
                "T - TEMPERATURE: Splash cold water on your face (30+ seconds) or hold an ice cube",
                "I - INTENSE EXERCISE: Do 20 jumping jacks, run in place, or sprint for 60 seconds",
                "P - PACED BREATHING: Exhale longer than you inhale (e.g., 4 in, 8 out)",
                "P - PAIRED RELAXATION: Tense muscles, then release while breathing out",
                "Choose one or combine as needed",
                "Continue until you feel a shift (usually 5-10 minutes)"
            ],
            "duration_minutes": 8,
            "difficulty": "EASY",
            "target_emotions": ["anxiety", "anger"],
            "why_it_works": "Temperature activates the 'dive reflex' slowing heart rate. Intense exercise burns off adrenaline. Paced breathing activates parasympathetic system. All work quickly because they change body chemistry.",
            "effectiveness": 0.92,
            "scientific_background": "Core DBT distress tolerance skill; based on physiological principles of emotion regulation."
        },
        {
            "name": "Check the Facts",
            "brief": "Evaluate if your emotion fits the situation",
            "description": "Examine whether your emotional response matches the actual facts of the situation, rather than assumptions or interpretations.",
            "steps": [
                "Ask: What event triggered my emotion?",
                "Ask: What are my interpretations, assumptions, or evaluations?",
                "Check the facts: Am I confusing a thought with a fact?",
                "Ask: Am I assuming a threat? What's the actual evidence?",
                "Ask: What's the worst that could happen? How likely is it?",
                "Ask: Does the intensity of my emotion fit the actual facts?",
                "If not, how can I reduce the emotion or respond differently?"
            ],
            "duration_minutes": 10,
            "difficulty": "MODERATE",
            "target_emotions": ["anger", "sadness"],
            "why_it_works": "Separates facts from interpretations, reducing emotionally-driven conclusions. Creates space between trigger and response.",
            "effectiveness": 0.85,
            "scientific_background": "DBT emotion regulation skill; based on cognitive-behavioral principles."
        },
        {
            "name": "Opposite Action",
            "brief": "Act opposite to your emotional urge",
            "description": "When an emotion doesn't fit the facts or acting on it won't be effective, do the opposite of what the emotion urges you to do.",
            "steps": [
                "Identify the emotion you're feeling",
                "What is this emotion urging you to do? (e.g., anger urges attack)",
                "Check the facts: Is the emotion justified by the facts?",
                "If NO, identify the OPPOSITE action",
                "Do the opposite action ALL THE WAY, with full attention",
                "Repeat until the emotion decreases",
                "Examples: When sad and wanting to isolate, reach out"
            ],
            "duration_minutes": 15,
            "difficulty": "HARD",
            "target_emotions": ["anger", "anxiety", "sadness"],
            "why_it_works": "Emotions and actions are linked in a feedback loop. Changing the action changes the emotion. Opposite action breaks the cycle.",
            "effectiveness": 0.86,
            "scientific_background": "Core DBT emotion regulation skill; supported by research on emotion-behavior connections."
        },
        {
            "name": "Radical Acceptance",
            "brief": "Accept reality as it is, without fighting it",
            "description": "Complete acceptance of reality with your mind, heart, and body. It doesn't mean approval - it means stopping the fight against what you cannot change.",
            "steps": [
                "Identify what you are fighting or struggling to accept",
                "Notice the physical sensations of non-acceptance (tension, tightness)",
                "Breathe into that tension as you say: 'It is what it is'",
                "Remind yourself: 'Fighting reality only increases suffering'",
                "Say: 'I can't change what's already happened'",
                "Ask: 'What would acceptance look like right now?'",
                "Turn your mind toward acceptance, again and again"
            ],
            "duration_minutes": 10,
            "difficulty": "HARD",
            "target_emotions": ["anger", "sadness"],
            "why_it_works": "Suffering = pain + non-acceptance. Pain is inevitable, but suffering is optional. Radical acceptance removes the suffering layer.",
            "effectiveness": 0.83,
            "scientific_background": "Core DBT distress tolerance skill; based on Zen Buddhist philosophy and acceptance-based therapies."
        },
        {
            "name": "STOP Skill",
            "brief": "Stop, Take a step back, Observe, Proceed mindfully",
            "description": "A crisis survival skill that prevents impulsive actions by inserting a pause between trigger and response.",
            "steps": [
                "S - STOP! Freeze, don't react. Your emotions may try to make you act without thinking.",
                "T - TAKE a step back. Step back from the situation. Take a breath. Give yourself space.",
                "O - OBSERVE. Notice what's happening inside and around you. What are you thinking? Feeling? What are others doing?",
                "P - PROCEED mindfully. Act with awareness. Ask: 'What will be most effective here?'"
            ],
            "duration_minutes": 2,
            "difficulty": "EASY",
            "target_emotions": ["anger"],
            "why_it_works": "Creates space between stimulus and response, allowing the prefrontal cortex to re-engage and make wiser decisions.",
            "effectiveness": 0.88,
            "scientific_background": "DBT crisis survival skill; based on mindfulness and impulse control research."
        },
        {
            "name": "IMPROVE the Moment",
            "brief": "Enhance the present moment when distressed",
            "description": "Use one or more strategies to make a difficult moment more bearable when you can't change the situation immediately.",
            "steps": [
                "I - Imagery: Imagine a peaceful scene or coping successfully",
                "M - Meaning: Find meaning or purpose in the struggle",
                "P - Prayer: Open your heart to a higher power or wisdom",
                "R - Relaxation: Do one relaxing thing (deep breath, stretch)",
                "O - One thing in the moment: Focus entirely on now",
                "V - Vacation: Take a short mental or physical break (5 min)",
                "E - Encouragement: Cheerlead yourself ('I can do this')",
                "Choose one or more and practice for a few minutes"
            ],
            "duration_minutes": 5,
            "difficulty": "EASY",
            "target_emotions": ["anxiety"],
            "why_it_works": "Provides multiple options to shift experience without avoiding the situation. Each option activates different brain regions that can reduce distress.",
            "effectiveness": 0.81,
            "scientific_background": "DBT distress tolerance skill; incorporates elements of positive psychology."
        },
        {
            "name": "Pros and Cons",
            "brief": "Compare consequences of acting vs. not acting on urges",
            "description": "Evaluate the advantages and disadvantages of tolerating distress vs. acting on harmful urges to strengthen motivation for healthy coping.",
            "steps": [
                "Draw a line down the middle of a page",
                "Left side: 'Acting on impulse/urge'",
                "Right side: 'Tolerating distress'",
                "List short-term pros and cons for acting",
                "List long-term pros and cons for acting",
                "List short-term pros and cons for tolerating",
                "List long-term pros and cons for tolerating",
                "Compare and choose based on which aligns with your goals"
            ],
            "duration_minutes": 10,
            "difficulty": "EASY",
            "target_emotions": ["anger"],
            "why_it_works": "Makes long-term consequences visible in moments when only short-term benefits are felt. Strengthens the wise mind decision-making.",
            "effectiveness": 0.82,
            "scientific_background": "DBT core skill; based on behavioral economics and decision science."
        },
        {
            "name": "Wise Mind",
            "brief": "Integrate emotion mind and reasonable mind",
            "description": "Access the wisdom that comes from integrating emotional experience with logical thinking - the intersection of 'knowing' and 'feeling'.",
            "steps": [
                "Sit comfortably and take a few deep breaths",
                "Ask: 'What is my EMOTIONAL MIND telling me?' (what I feel)",
                "Ask: 'What is my REASONABLE MIND telling me?' (what I think)",
                "Imagine these two minds coming together",
                "Ask: 'What does my WISE MIND know?'",
                "Notice the answer that arises - it might be a gut feeling, an image, or words",
                "Trust this wise knowing, even if it's different from either extreme"
            ],
            "duration_minutes": 8,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety"],
            "why_it_works": "Integrates intuitive/emotional knowing with logical analysis, creating decisions that honor both. Wise mind often feels calm and certain.",
            "effectiveness": 0.84,
            "scientific_background": "Central concept in DBT; integrates Eastern wisdom traditions with Western psychology."
        }
    ]
    
    for tech in dbt_techniques:
        tech["categoryId"] = categories["DBT"]
        all_techniques.append(tech)
    
    # ----------------------------------------------------------------------
    # CATEGORY 5: JOURNALING TECHNIQUES (8 techniques)
    # ----------------------------------------------------------------------
    
    journaling_techniques = [
        {
            "name": "Gratitude Journaling",
            "brief": "Daily practice of noting things you're grateful for",
            "description": "A simple but powerful practice of regularly writing down things you're grateful for, which rewires the brain to notice positives more readily.",
            "steps": [
                "Find a quiet moment, ideally morning or evening",
                "Write the date at the top of a page",
                "List 3-5 things you're grateful for today",
                "For each, write 1-2 sentences about WHY you're grateful",
                "Be specific rather than general ('my friend called when I was sad')",
                "Include at least one small, everyday thing (a good cup of coffee)",
                "Notice how your mood shifts as you write",
                "Make this a daily habit for best results"
            ],
            "duration_minutes": 10,
            "difficulty": "EASY",
            "target_emotions": ["sadness"],
            "why_it_works": "Counteracts the brain's negativity bias by intentionally focusing on positives. Over time, this builds neural pathways that make noticing positives more automatic.",
            "effectiveness": 0.87,
            "scientific_background": "Extensively researched by Robert Emmons and others; shows significant increases in well-being and life satisfaction."
        },
        {
            "name": "Stream of Consciousness",
            "brief": "Unfiltered, continuous writing to process emotions",
            "description": "Write continuously without stopping, editing, or judging, allowing thoughts and feelings to flow onto the page for emotional release and clarity.",
            "steps": [
                "Set a timer for 10-20 minutes",
                "Write continuously without stopping",
                "Don't worry about grammar, spelling, or making sense",
                "If you get stuck, write 'I don't know what to write' until something comes",
                "Write whatever comes to mind - thoughts, feelings, memories",
                "Don't censor or judge anything that emerges",
                "When timer ends, you can keep or destroy what you wrote",
                "Take a few deep breaths afterward"
            ],
            "duration_minutes": 15,
            "difficulty": "EASY",
            "target_emotions": ["anxiety"],
            "why_it_works": "Externalizes internal experience, reducing cognitive load and emotional intensity. The physical act of writing helps process and organize thoughts.",
            "effectiveness": 0.82,
            "scientific_background": "Similar to expressive writing research by James Pennebaker; shown to improve immune function and reduce doctor visits."
        },
        {
            "name": "Cognitive Distortion Journal",
            "brief": "Identify and challenge thinking errors",
            "description": "A structured journaling practice to catch and challenge cognitive distortions in daily life, with a simple format you can use anytime.",
            "steps": [
                "Create four columns in your journal",
                "Column 1: 'Situation' - what happened?",
                "Column 2: 'Automatic Thought' - what went through your mind?",
                "Column 3: 'Cognitive Distortion' - which distortion is it?",
                "Column 4: 'Balanced Thought' - a more realistic perspective",
                "Fill this out whenever you notice a mood shift",
                "Review weekly to identify patterns"
            ],
            "duration_minutes": 12,
            "difficulty": "MODERATE",
            "target_emotions": ["anxiety", "sadness", "anger"],
            "why_it_works": "Creates a consistent practice of cognitive restructuring, making it automatic over time. Written record helps identify patterns.",
            "effectiveness": 0.85,
            "scientific_background": "Based on CBT principles; journaling enhances therapy outcomes significantly."
        },
        {
            "name": "Self-Compassion Letter",
            "brief": "Write to yourself with kindness and understanding",
            "description": "Write a letter to yourself from a place of compassion, as you would write to a dear friend who is struggling with the same issue.",
            "steps": [
                "Think of something you're struggling with or criticizing yourself about",
                "Imagine a dear friend is going through the exact same thing",
                "Write a letter to that friend, offering kindness and support",
                "Now write the same letter to YOURSELF",
                "Acknowledge the pain: 'This is really hard and it's okay to struggle'",
                "Remind yourself you're not alone in this experience",
                "Offer encouragement: 'May you be gentle with yourself'",
                "Read the letter aloud to yourself",
                "Notice how you feel"
            ],
            "duration_minutes": 15,
            "difficulty": "MODERATE",
            "target_emotions": ["sadness"],
            "why_it_works": "Activates the self-compassion system in the brain, which reduces cortisol and increases oxytocin. Counteracts the inner critic.",
            "effectiveness": 0.86,
            "scientific_background": "Based on Kristin Neff and Chris Germer's self-compassion research; reduces depression and anxiety."
        },
        {
            "name": "One-Sentence Journal",
            "brief": "Minimalist journaling for daily consistency",
            "description": "A low-barrier journaling practice where you write just one sentence per day, making it sustainable even when motivation is low.",
            "steps": [
                "At the end of each day, write ONE sentence",
                "It can be about anything: how you felt, what happened, something you learned",
                "Don't worry about making it profound - just honest",
                "Examples: 'Today was hard but I got through it'",
                "'I felt anxious this morning but better after my walk'",
                "'Grateful for my friend checking in on me'",
                "That's it - one sentence, every day"
            ],
            "duration_minutes": 2,
            "difficulty": "EASY",
            "target_emotions": ["sadness"],
            "why_it_works": "Removes all barriers to journaling. The consistency builds a record of your emotional life and creates small moments of reflection.",
            "effectiveness": 0.78,
            "scientific_background": "Based on habit formation research; tiny habits are more sustainable than ambitious ones."
        },
        {
            "name": "Emotion Tracking",
            "brief": "Track emotions to identify patterns and triggers",
            "description": "A structured way to track your emotions throughout the day, helping you identify patterns, triggers, and what helps or hurts.",
            "steps": [
                "Create a simple tracking sheet with time, emotion, intensity (1-10), trigger, and what helped",
                "Check in with yourself 3-4 times daily (morning, afternoon, evening)",
                "Record your primary emotion and its intensity",
                "Note what was happening just before (trigger)",
                "Note anything you did that helped or hurt",
                "Review weekly to identify patterns",
                "Use insights to plan coping strategies"
            ],
            "duration_minutes": 10,
            "difficulty": "EASY",
            "target_emotions": ["anxiety"],
            "why_it_works": "Creates awareness of emotional patterns, which is the first step in regulation. The data helps identify effective strategies.",
            "effectiveness": 0.80,
            "scientific_background": "Used in mood disorders treatment; increases emotional awareness and prediction of episodes."
        },
        {
            "name": "Unsent Letter",
            "brief": "Write what you can't say to someone",
            "description": "Write a letter to someone expressing everything you wish you could say, without actually sending it, for emotional release and clarity.",
            "steps": [
                "Think of someone you have unresolved feelings toward",
                "Write them a letter expressing EVERYTHING - the good, the bad, the hurt",
                "Don't hold back or edit yourself",
                "Say everything you wish you could say to them directly",
                "Include your feelings, your needs, your hurts",
                "When finished, decide what to do with it: keep, destroy, or revise",
                "Do NOT send it (this is for you, not them)"
            ],
            "duration_minutes": 20,
            "difficulty": "MODERATE",
            "target_emotions": ["anger", "sadness"],
            "why_it_works": "Provides emotional release without the consequences of direct confrontation. Helps process feelings and gain clarity about what you need.",
            "effectiveness": 0.83,
            "scientific_background": "Used in grief counseling and trauma therapy; facilitates emotional processing."
        },
        {
            "name": "Morning Pages",
            "brief": "Three pages of stream-of-consciousness each morning",
            "description": "A daily practice of writing three pages of longhand, stream-of-consciousness writing first thing in the morning to clear the mind and access creativity.",
            "steps": [
                "Write three pages of longhand, stream-of-consciousness writing every morning",
                "Write whatever comes to mind - don't censor or edit",
                "Don't worry about quality, grammar, or coherence",
                "If you have nothing to say, write 'I have nothing to say' until something comes",
                "Do this before any other creative work",
                "Don't read what you've written for at least 8 weeks",
                "The goal is not to create art but to clear your mind"
            ],
            "duration_minutes": 25,
            "difficulty": "HARD",
            "target_emotions": ["anxiety"],
            "why_it_works": "Clears the mind of clutter and worries, allowing for greater clarity and creativity. Externalizes anxious thoughts so they don't loop internally.",
            "effectiveness": 0.79,
            "scientific_background": "Developed by Julia Cameron in 'The Artist's Way'; millions have used it for decades."
        }
    ]
    
    for tech in journaling_techniques:
        tech["categoryId"] = categories["Journaling"]
        all_techniques.append(tech)
    
    # ----------------------------------------------------------------------
    # CATEGORY 6: BEHAVIORAL ACTIVATION TECHNIQUES (8 techniques)
    # ----------------------------------------------------------------------
    
    behavioral_techniques = [
        {
            "name": "Pleasant Activity Scheduling",
            "brief": "Schedule activities that bring joy or meaning",
            "description": "Deliberately plan and schedule pleasant or meaningful activities to increase positive reinforcement and break the cycle of avoidance and low mood.",
            "steps": [
                "List 10-20 activities you used to enjoy or might enjoy",
                "Rate each for expected pleasure (0-10) and mastery (0-10)",
                "Choose 3-5 activities to schedule this week",
                "Put them in your calendar like any important appointment",
                "Do the activity even if you don't feel like it at first",
                "Rate actual pleasure and mastery after completion",
                "Notice that actual ratings are often higher than expected",
                "Repeat weekly, gradually increasing"
            ],
            "duration_minutes": 20,
            "difficulty": "MODERATE",
            "target_emotions": ["sadness"],
            "why_it_works": "Depression creates a cycle: low mood → less activity → less positive reinforcement → lower mood. This breaks that cycle by ensuring activity regardless of mood.",
            "effectiveness": 0.88,
            "scientific_background": "Core Behavioral Activation technique; as effective as medication for depression in multiple studies."
        },
        {
            "name": "Micro-Activities",
            "brief": "Tiny actions when even small tasks feel overwhelming",
            "description": "Break activities down into the smallest possible steps (2-5 minutes) and do just one, building momentum without overwhelming yourself.",
            "steps": [
                "Identify something you need or want to do",
                "Break it into the SMALLEST possible step (2-5 minutes)",
                "Examples: 'Wash 3 dishes' not 'clean kitchen'",
                "'Put on shoes' not 'go for a run'",
                "'Open laptop' not 'write report'",
                "Do just that one tiny step",
                "Rate your mood before and after",
                "If you want, do one more tiny step"
            ],
            "duration_minutes": 5,
            "difficulty": "EASY",
            "target_emotions": ["anxiety"],
            "why_it_works": "Removes the overwhelm that prevents action. Success with tiny steps builds momentum and self-efficacy. Often one step leads to another.",
            "effectiveness": 0.86,
            "scientific_background": "Based on behavioral activation and motivation research; small wins trigger dopamine release."
        },
        {
            "name": "Activity-Mood Monitoring",
            "brief": "Track activities and mood to identify patterns",
            "description": "Track what you do and how you feel to discover which activities improve or worsen your mood, then do more of what helps.",
            "steps": [
                "Create a simple hourly log",
                "Each hour, record: what you did and your mood (0-10)",
                "Do this for one week",
                "At week's end, review to find patterns",
                "Which activities are associated with better mood?",
                "Which activities are associated with worse mood?",
                "Plan to increase activities linked to better mood",
                "Plan to modify or reduce activities linked to worse mood"
            ],
            "duration_minutes": 5,
            "difficulty": "EASY",
            "target_emotions": ["sadness"],
            "why_it_works": "Provides objective data about what actually helps, rather than relying on assumptions. Depression often distorts perception of activities.",
            "effectiveness": 0.81,
            "scientific_background": "Standard Behavioral Activation tool; helps identify the function of behaviors."
        },
        {
            "name": "Values-Based Action",
            "brief": "Take action aligned with what matters most",
            "description": "Identify your core values and take small actions that align with them, creating meaning and purpose even when mood is low.",
            "steps": [
                "List 3-5 values that matter most to you (family, health, growth, connection, etc.)",
                "For each, rate how well you're living that value (0-10)",
                "Choose one value to focus on this week",
                "Brainstorm 3 small actions that would honor that value",
                "Pick ONE to do today",
                "Do it, even if you don't feel like it",
                "Notice how it feels to act on your values"
            ],
            "duration_minutes": 15,
            "difficulty": "MODERATE",
            "target_emotions": ["sadness"],
            "why_it_works": "Connects daily actions to deeper meaning, which increases motivation and satisfaction even when pleasure is low.",
            "effectiveness": 0.85,
            "scientific_background": "Integration of Behavioral Activation with Acceptance and Commitment Therapy (ACT); values-based living improves well-being."
        },
        {
            "name": "Behavioral Experiments",
            "brief": "Test beliefs that keep you stuck",
            "description": "Design small experiments to test beliefs that prevent action, such as 'I'll feel worse if I try' or 'Nothing will help'.",
            "steps": [
                "Identify a belief that's keeping you from acting (e.g., 'I'll feel worse if I go out')",
                "Rate how strongly you believe it (0-100%)",
                "Design a small experiment to test it (specific, doable, measurable)",
                "Predict what will happen (rate expected mood, etc.)",
                "Conduct the experiment",
                "Record what actually happened (rate actual mood)",
                "Compare prediction to outcome",
                "Update your belief based on evidence"
            ],
            "duration_minutes": 30,
            "difficulty": "HARD",
            "target_emotions": ["anxiety"],
            "why_it_works": "Directly challenges beliefs with evidence, which is more powerful than just talking about them. Often shows that things aren't as bad as predicted.",
            "effectiveness": 0.84,
            "scientific_background": "Core in both CBT and Behavioral Activation; reduces avoidance and builds confidence."
        },
        {
            "name": "Energy Management",
            "brief": "Match activities to your energy levels",
            "description": "Learn to work with your energy rather than against it by matching tasks to your current energy level, preventing burnout and building momentum.",
            "steps": [
                "Rate your current energy (1-10)",
                "If LOW (1-3): Choose tiny, easy tasks (2-5 minutes)",
                "If MEDIUM (4-6): Choose moderate, engaging tasks (15-30 minutes)",
                "If HIGH (7-10): Tackle challenging tasks",
                "Set a timer appropriate to your energy",
                "Do the task without judgment",
                "Take a break when timer ends",
                "Reassess energy and adjust as needed"
            ],
            "duration_minutes": 20,
            "difficulty": "EASY",
            "target_emotions": ["sadness"],
            "why_it_works": "Prevents the all-or-nothing pattern of doing nothing or overdoing. Respects natural energy rhythms while maintaining some activity.",
            "effectiveness": 0.82,
            "scientific_background": "Based on energy management research; used in chronic fatigue and depression treatment."
        },
        {
            "name": "Anti-Procrastination List",
            "brief": "Break tasks into steps and start with the easiest",
            "description": "A structured approach to overcoming procrastination by listing tasks, breaking them down, and starting with the smallest, easiest step.",
            "steps": [
                "Write down everything you're procrastinating on",
                "For each item, break it into SMALL steps (2-5 minutes each)",
                "Rate each step for difficulty (1-10)",
                "Pick the step with the LOWEST difficulty rating",
                "Do that step right now (set a timer if needed)",
                "Cross it off and notice how you feel",
                "If you want, do another small step",
                "Celebrate each completion"
            ],
            "duration_minutes": 10,
            "difficulty": "EASY",
            "target_emotions": ["anxiety"],
            "why_it_works": "Overcomes the paralysis of large tasks by making the first step so small it's nearly impossible to resist. Momentum builds naturally.",
            "effectiveness": 0.87,
            "scientific_background": "Based on behavioral activation and motivation research; small starts trigger the Zeigarnik effect (need to complete tasks)."
        },
        {
            "name": "Routine Building",
            "brief": "Establish daily routines that support well-being",
            "description": "Create simple daily routines that provide structure and support mental health, especially important when mood makes structure feel difficult.",
            "steps": [
                "Identify 3-4 key times in your day (morning, midday, evening, bedtime)",
                "For each, choose 1-2 small, consistent actions",
                "Morning: wake time, make bed, wash face",
                "Midday: lunch break, short walk",
                "Evening: dinner, connect with someone",
                "Bedtime: screen off 30 min before, read, gratitude",
                "Start with just ONE routine for one week",
                "Add another when first feels automatic",
                "Be consistent, not perfect"
            ],
            "duration_minutes": 15,
            "difficulty": "MODERATE",
            "target_emotions": ["sadness"],
            "why_it_works": "Routines reduce decision fatigue and provide structure when internal motivation is low. Consistent routines stabilize mood over time.",
            "effectiveness": 0.83,
            "scientific_background": "Routines are crucial in mood disorder management; supported by research on circadian rhythms and behavioral activation."
        }
    ]
    
    for tech in behavioral_techniques:
        tech["categoryId"] = categories["Behavioral Activation"]
        all_techniques.append(tech)
    
    # ============================================
    # INSERT ALL TECHNIQUES
    # ============================================
    
    print(f"\n[SEED] Inserting {len(all_techniques)} techniques...")
    
    inserted_count = 0
    existing_count = 0
    
    for tech_data in all_techniques:
        category_name = next(
            (cat_name for cat_name, cat_db_id in categories.items() if cat_db_id == tech_data["categoryId"]),
            "",
        )
        annotate_technique_dict(tech_data, category_name)
        metadata_fields = prisma_metadata_fields(tech_data, category_name)

        # Check if exists first
        existing = await prisma.technique.find_first(
            where={"name": tech_data["name"]}
        )
        
        if existing:
            existing_count += 1
            await prisma.technique.update(
                where={"id": existing.id},
                data={
                    "targetEmotions": normalize_target_emotions(target_emotions_for_technique(tech_data, category_name)),
                    **metadata_fields,
                },
            )
            print(f"  [✓] Exists: {tech_data['name']}")
        else:
            # Prepare data for Prisma
            create_data = {
                "categoryId": tech_data["categoryId"],
                "name": tech_data["name"],
                "brief": tech_data["brief"],
                "description": tech_data["description"],
                "steps": tech_data["steps"],
                "durationMinutes": tech_data["duration_minutes"],
                "difficulty": tech_data["difficulty"],
                "targetEmotions": normalize_target_emotions(target_emotions_for_technique(tech_data, category_name)),
                "whyItWorks": tech_data["why_it_works"],
                "effectiveness": tech_data["effectiveness"],
                "isActive": True,
                **metadata_fields,
            }
            
            await prisma.technique.create(data=create_data)
            inserted_count += 1
            print(f"  [✨] Created: {tech_data['name']}")
    
    # ============================================
    # SUMMARY
    # ============================================
    
    print("\n" + "="*70)
    print("  SEEDING COMPLETE")
    print("="*70)
    print(f"  Categories: {len(categories_data)}")
    print(f"  Techniques total: {len(all_techniques)}")
    print(f"    • Inserted: {inserted_count}")
    print(f"    • Already existed: {existing_count}")
    print("\n  Techniques by category:")
    
    category_counts = {}
    for tech in all_techniques:
        cat_id = tech["categoryId"]
        for cat_name, cat_db_id in categories.items():
            if cat_db_id == cat_id:
                category_counts[cat_name] = category_counts.get(cat_name, 0) + 1
    
    for cat_name, count in category_counts.items():
        print(f"    • {cat_name}: {count} techniques")
    
    print("="*70)
    
    await prisma.disconnect()


if __name__ == "__main__":
    asyncio.run(seed_techniques())

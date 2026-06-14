"""
Seed a focused set of research-backed techniques for SentiMind.

These fill gaps in the existing 108-technique library around CBT-I sleep
support, ACT-style defusion, catastrophic exam thoughts, and DBT self-soothing.
The script is idempotent: existing techniques are updated, missing techniques
are created.
"""

import asyncio
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mental_health_wellness.db.client import close_prisma_client, get_prisma_client  # noqa: E402


TECHNIQUES = [
    {
        "name": "Brain Dump Before Sleep",
        "category": "Journaling",
        "brief": "Unload bedtime worries onto paper so the mind does not keep rehearsing them in bed.",
        "description": (
            "A short pre-sleep writing exercise for scattered worries, exam thoughts, and mental loops. "
            "The user writes worries, marks what can wait, and chooses one small next step for tomorrow."
        ),
        "steps": [
            "Set a 5 minute timer before getting into bed.",
            "Write every worry or exam thought without organizing it.",
            "Circle anything that needs action tomorrow, not tonight.",
            "Write one tiny next step beside the most important item.",
            "Close the note and use a simple phrase: 'This is parked for tomorrow.'",
        ],
        "durationMinutes": 5,
        "difficulty": "EASY",
        "targetEmotions": ["ANXIETY", "SADNESS"],
        "targetSubEmotions": ["bedtime_rumination", "racing_thoughts", "worry", "academic_pressure", "fear_of_failure"],
        "targetSymptoms": ["sleep_difficulty", "bedtime_racing_thoughts"],
        "targetBehaviors": ["rumination"],
        "avoidSubEmotions": ["panic_now"],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.1,
        "maxIntensity": 0.65,
        "pacingTier": "slow",
        "deliveryMode": "reflection",
        "bestForContexts": ["thought_unloading", "bedtime_rumination", "sleep_difficulty", "nighttime_worry", "exam_week", "exam_pressure", "academic_anxiety"],
        "whyItWorks": "Writing worries down externalizes mental loops and supports scheduled problem solving instead of trying to solve everything at bedtime.",
        "effectiveness": 0.78,
    },
    {
        "name": "Thought Defusion",
        "category": "Mindfulness",
        "brief": "Create distance from sticky thoughts by noticing them as mental events, not facts.",
        "description": (
            "An ACT-style technique for thoughts that feel loud, sticky, or convincing. "
            "Instead of debating the thought, the user practices changing their relationship to it."
        ),
        "steps": [
            "Name the thought in one sentence.",
            "Add the phrase: 'I am having the thought that...'",
            "Repeat it slowly and notice the small distance this creates.",
            "Ask: 'Is this thought trying to protect me, predict danger, or demand certainty?'",
            "Return attention to one present-moment anchor.",
        ],
        "durationMinutes": 4,
        "difficulty": "EASY",
        "targetEmotions": ["ANXIETY", "FEAR", "SADNESS"],
        "targetSubEmotions": ["rumination", "racing_thoughts", "worry", "catastrophizing", "fortune_telling", "fear_of_failure", "future_threat", "bedtime_rumination"],
        "targetSymptoms": ["bedtime_racing_thoughts"],
        "targetBehaviors": ["rumination"],
        "avoidSubEmotions": [],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.15,
        "maxIntensity": 0.75,
        "pacingTier": "normal",
        "deliveryMode": "exercise",
        "bestForContexts": ["defusion", "cognitive_defusion", "thought_observation", "rumination_interrupt", "metacognitive_awareness", "bedtime_rumination", "catastrophic_exam_thought"],
        "whyItWorks": "Defusion reduces the believability and grip of distressing thoughts without forcing the user to argue with them.",
        "effectiveness": 0.76,
    },
    {
        "name": "Leaves on a Stream",
        "category": "Mindfulness",
        "brief": "Let thoughts pass through awareness without chasing, proving, or suppressing them.",
        "description": (
            "A gentle cognitive defusion visualization for worry loops and bedtime rumination. "
            "It is useful when analytical CBT feels too effortful."
        ),
        "steps": [
            "Picture a slow stream with leaves floating by.",
            "When a thought appears, place it on a leaf.",
            "Let the leaf move at its own pace without pushing it away.",
            "If attention gets pulled in, gently place that reaction on another leaf.",
            "Continue for a few minutes, returning to the stream each time.",
        ],
        "durationMinutes": 6,
        "difficulty": "EASY",
        "targetEmotions": ["ANXIETY", "FEAR", "SADNESS"],
        "targetSubEmotions": ["rumination", "racing_thoughts", "worry", "bedtime_rumination", "catastrophizing", "future_threat"],
        "targetSymptoms": ["sleep_difficulty", "bedtime_racing_thoughts"],
        "targetBehaviors": ["rumination"],
        "avoidSubEmotions": [],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.1,
        "maxIntensity": 0.7,
        "pacingTier": "slow",
        "deliveryMode": "exercise",
        "bestForContexts": ["cognitive_defusion", "thought_observation", "rumination_interrupt", "bedtime_rumination", "sleep_difficulty", "nighttime_worry"],
        "whyItWorks": "The visualization trains observing thoughts instead of fusing with them, a core mechanism in acceptance-based approaches.",
        "effectiveness": 0.74,
    },
    {
        "name": "Stimulus Control for Sleep",
        "category": "CBT",
        "brief": "Rebuild the bed as a cue for sleep rather than worry, studying, or mental problem solving.",
        "description": (
            "A CBT-I technique for sleep difficulty when the bed has become linked with wakefulness, frustration, or exam worry."
        ),
        "steps": [
            "Use the bed mainly for sleep, not studying or extended worrying.",
            "If you are awake and stuck in worry, leave the bed briefly.",
            "Do something quiet and dim until sleepiness returns.",
            "Return to bed only when sleepy.",
            "Keep the wake-up time consistent tomorrow.",
        ],
        "durationMinutes": 10,
        "difficulty": "MODERATE",
        "targetEmotions": ["ANXIETY", "SADNESS"],
        "targetSubEmotions": ["bedtime_rumination", "restlessness", "worry", "stress"],
        "targetSymptoms": ["sleep_difficulty", "sleep_disruption"],
        "targetBehaviors": ["avoidance"],
        "avoidSubEmotions": ["panic_now"],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.1,
        "maxIntensity": 0.65,
        "pacingTier": "slow",
        "deliveryMode": "plan",
        "bestForContexts": ["sleep_onset", "sleep_environment", "bedtime_wind_down", "bedtime_rumination", "sleep_difficulty", "nighttime_worry"],
        "whyItWorks": "Stimulus control is a core CBT-I component that weakens the learned bed-worry association and strengthens bed-sleep cues.",
        "effectiveness": 0.82,
    },
    {
        "name": "Sleep Wind-Down Routine",
        "category": "Behavioral Activation",
        "brief": "Create a predictable pre-sleep routine that lowers cognitive and physical activation.",
        "description": (
            "A practical bedtime sequence for exam week, stress, and late-night overthinking. "
            "It pairs light planning with low-stimulation cues before bed."
        ),
        "steps": [
            "Choose a 20 minute wind-down window before bed.",
            "Write tomorrow's first study step on one line.",
            "Move phone or study material away from the bed.",
            "Do one low-light calming activity.",
            "Repeat the same closing cue each night.",
        ],
        "durationMinutes": 20,
        "difficulty": "EASY",
        "targetEmotions": ["ANXIETY", "SADNESS"],
        "targetSubEmotions": ["bedtime_rumination", "stress", "worry", "restlessness", "academic_pressure"],
        "targetSymptoms": ["sleep_difficulty", "sleep_disruption"],
        "targetBehaviors": [],
        "avoidSubEmotions": ["panic_now"],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.1,
        "maxIntensity": 0.6,
        "pacingTier": "slow",
        "deliveryMode": "plan",
        "bestForContexts": ["sleep_onset", "bedtime_wind_down", "sleep_difficulty", "nighttime_worry", "exam_week", "academic_anxiety"],
        "whyItWorks": "A consistent wind-down routine reduces pre-sleep arousal and gives worry/planning a place before the user reaches bed.",
        "effectiveness": 0.75,
    },
    {
        "name": "Constructive Worry Worksheet",
        "category": "CBT",
        "brief": "Turn repeated worry into one solvable next step and one unsolved item to park.",
        "description": (
            "A structured worry-management worksheet for future-focused anxiety and bedtime problem solving."
        ),
        "steps": [
            "Write the worry as a question.",
            "Mark it as solvable, partly solvable, or not solvable right now.",
            "For solvable parts, choose the smallest next action.",
            "For unsolved parts, write what information or time is needed.",
            "Schedule when you will revisit it.",
        ],
        "durationMinutes": 8,
        "difficulty": "MODERATE",
        "targetEmotions": ["ANXIETY", "FEAR"],
        "targetSubEmotions": ["worry", "rumination", "bedtime_rumination", "academic_pressure", "future_threat", "fear_of_failure"],
        "targetSymptoms": ["sleep_difficulty", "bedtime_racing_thoughts"],
        "targetBehaviors": ["rumination", "procrastination"],
        "avoidSubEmotions": ["panic_now"],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.15,
        "maxIntensity": 0.7,
        "pacingTier": "normal",
        "deliveryMode": "worksheet",
        "bestForContexts": ["scheduled_worry", "worry_containment", "practical_problem_solving", "bedtime_rumination", "exam_week", "exam_pressure", "academic_anxiety"],
        "whyItWorks": "Constructive worry separates actionable concerns from unsolvable loops, reducing the brain's urge to rehearse the same worry.",
        "effectiveness": 0.79,
    },
    {
        "name": "Decatastrophizing Questions",
        "category": "CBT",
        "brief": "Slow down a worst-case prediction and test how likely, survivable, and manageable it is.",
        "description": (
            "A CBT technique for thoughts such as 'I might fail and drop out' where the mind jumps to the worst possible outcome."
        ),
        "steps": [
            "Write the feared outcome in one sentence.",
            "Ask: What is the most likely outcome, not only the worst?",
            "Ask: If the feared thing happened, what could I do next?",
            "Ask: What evidence makes this less certain than it feels?",
            "Write a balanced coping statement.",
        ],
        "durationMinutes": 8,
        "difficulty": "MODERATE",
        "targetEmotions": ["ANXIETY", "FEAR"],
        "targetSubEmotions": ["catastrophizing", "fortune_telling", "fear_of_failure", "future_threat", "academic_pressure"],
        "targetSymptoms": [],
        "targetBehaviors": ["rumination"],
        "avoidSubEmotions": ["panic_now"],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.2,
        "maxIntensity": 0.75,
        "pacingTier": "normal",
        "deliveryMode": "worksheet",
        "bestForContexts": ["catastrophising_correction", "belief_challenge", "catastrophic_exam_thought", "specific_exam_failure_belief", "academic_risk", "exam_pressure"],
        "whyItWorks": "Decatastrophizing is a cognitive restructuring method that tests probability and coping ability instead of treating fear as fact.",
        "effectiveness": 0.81,
    },
    {
        "name": "Coping Card for Catastrophic Thoughts",
        "category": "CBT",
        "brief": "Create a short card with evidence, balanced wording, and one action for recurring scary thoughts.",
        "description": (
            "A quick CBT support for recurring catastrophic thoughts that show up under stress or at night."
        ),
        "steps": [
            "Write the recurring scary thought.",
            "Write one evidence-based reminder that makes it less certain.",
            "Write one coping action you can take in the next 10 minutes.",
            "Write one supportive sentence you would say to a friend.",
            "Keep the card ready for the next time the thought appears.",
        ],
        "durationMinutes": 7,
        "difficulty": "EASY",
        "targetEmotions": ["ANXIETY", "FEAR", "SADNESS"],
        "targetSubEmotions": ["catastrophizing", "fortune_telling", "fear_of_failure", "future_threat", "panic", "worry"],
        "targetSymptoms": [],
        "targetBehaviors": ["rumination"],
        "avoidSubEmotions": [],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.2,
        "maxIntensity": 0.8,
        "pacingTier": "normal",
        "deliveryMode": "plan",
        "bestForContexts": ["belief_challenge", "catastrophic_exam_thought", "specific_exam_failure_belief", "academic_risk", "panic_coping", "exam_pressure"],
        "whyItWorks": "Coping cards make balanced thinking available during high arousal, when working memory and flexible thinking are harder to access.",
        "effectiveness": 0.76,
    },
    {
        "name": "Self-Soothing with Five Senses",
        "category": "DBT",
        "brief": "Use simple sensory cues to reduce distress without arguing with the feeling.",
        "description": (
            "A DBT distress tolerance technique for high emotion, shame, fear, anger, or overwhelm."
        ),
        "steps": [
            "Choose one soothing cue for sight.",
            "Choose one for sound.",
            "Choose one for touch.",
            "Choose one for smell or taste if available.",
            "Spend one minute with each cue, describing it simply.",
        ],
        "durationMinutes": 5,
        "difficulty": "EASY",
        "targetEmotions": ["ANXIETY", "FEAR", "ANGER", "SADNESS", "DISGUST"],
        "targetSubEmotions": ["distress", "panic", "overwhelm", "shame", "grief", "anger", "fear"],
        "targetSymptoms": ["tension", "restlessness"],
        "targetBehaviors": [],
        "avoidSubEmotions": [],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.25,
        "maxIntensity": 0.85,
        "pacingTier": "normal",
        "deliveryMode": "exercise",
        "bestForContexts": ["nervous_system_regulation", "distress_tolerance", "grounding", "emotion_regulation"],
        "whyItWorks": "Sensory self-soothing redirects attention toward regulating cues, a DBT distress tolerance strategy for intense emotion.",
        "effectiveness": 0.73,
    },
    {
        "name": "Exam Coping Plan",
        "category": "CBT",
        "brief": "Break exam pressure into controllable study actions, coping steps, and support options.",
        "description": (
            "A practical plan for academic anxiety, fear of failure, and overwhelm before an exam."
        ),
        "steps": [
            "Name the exam worry in one sentence.",
            "List what is controllable before the exam.",
            "Choose the first 20 minute study action.",
            "Choose one coping step for worry spikes.",
            "Choose who or what you can use for support if you feel stuck.",
        ],
        "durationMinutes": 10,
        "difficulty": "MODERATE",
        "targetEmotions": ["ANXIETY", "FEAR"],
        "targetSubEmotions": ["academic_pressure", "fear_of_failure", "future_threat", "worry", "overwhelm", "procrastination"],
        "targetSymptoms": [],
        "targetBehaviors": ["procrastination", "avoidance", "task_starting"],
        "avoidSubEmotions": ["panic_now"],
        "avoidSymptoms": [],
        "avoidBehaviors": [],
        "minIntensity": 0.2,
        "maxIntensity": 0.75,
        "pacingTier": "normal",
        "deliveryMode": "plan",
        "bestForContexts": ["exam_week", "exam_pressure", "academic_anxiety", "academic_risk", "practical_problem_solving", "pre_performance"],
        "whyItWorks": "Planning reduces uncertainty by separating controllable study behavior from uncontrollable predictions.",
        "effectiveness": 0.77,
    },
]


async def seed_research_backed_techniques() -> None:
    prisma = await get_prisma_client()
    categories = await prisma.techniquecategory.find_many()
    category_ids = {category.name: category.id for category in categories}

    inserted = 0
    updated = 0
    missing_categories: set[str] = set()

    for technique in TECHNIQUES:
        category = technique["category"]
        category_id = category_ids.get(category)
        if not category_id:
            missing_categories.add(category)
            continue

        data = {
            "categoryId": category_id,
            "name": technique["name"],
            "brief": technique["brief"],
            "description": technique["description"],
            "steps": technique["steps"],
            "durationMinutes": technique["durationMinutes"],
            "difficulty": technique["difficulty"],
            "targetEmotions": technique["targetEmotions"],
            "targetSubEmotions": technique["targetSubEmotions"],
            "targetSymptoms": technique["targetSymptoms"],
            "targetBehaviors": technique["targetBehaviors"],
            "avoidSubEmotions": technique["avoidSubEmotions"],
            "avoidSymptoms": technique["avoidSymptoms"],
            "avoidBehaviors": technique["avoidBehaviors"],
            "minIntensity": technique["minIntensity"],
            "maxIntensity": technique["maxIntensity"],
            "pacingTier": technique["pacingTier"],
            "deliveryMode": technique["deliveryMode"],
            "bestForContexts": technique["bestForContexts"],
            "whyItWorks": technique["whyItWorks"],
            "effectiveness": technique["effectiveness"],
            "safeAtSeverity": ["MINIMAL", "MILD", "MODERATE", "MODERATELY_SEVERE"],
            "contraindicatedFlags": ["suicidal_ideation"],
            "isActive": True,
        }

        existing = await prisma.technique.find_first(where={"name": technique["name"]})
        if existing:
            await prisma.technique.update(where={"id": existing.id}, data=data)
            updated += 1
            print(f"[SEED] Updated: {technique['name']}")
        else:
            await prisma.technique.create(data=data)
            inserted += 1
            print(f"[SEED] Created: {technique['name']}")

    if missing_categories:
        print(f"[SEED] Missing categories skipped: {sorted(missing_categories)}")
    print(f"[SEED] Complete | inserted={inserted} updated={updated}")


async def main() -> None:
    try:
        await seed_research_backed_techniques()
    finally:
        await close_prisma_client()


if __name__ == "__main__":
    asyncio.run(main())

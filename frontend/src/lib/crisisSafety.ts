export type CrisisSafetyStatus = 'safe' | 'danger' | 'unknown'

export const POST_CRISIS_SAFETY_PROMPT =
  "Before we continue, I need to check your immediate safety. Are you safe right now, or are you still in danger? Please reply with something like \"I'm safe\" or \"I'm still in danger.\" Once you confirm you're safe, we can continue with what you were saying."

export const POST_CRISIS_DANGER_PROMPT =
  "I'm really concerned that you may still be in immediate danger. Please move away from anything you could use to hurt yourself if you can, call local emergency services now, or stay with another person. Are you safe right now?"

const DANGER_PATTERNS = [
  /\b(?:not safe|unsafe|still in danger|in danger|im in danger|i am in danger)\b/i,
  /\b(?:not okay|not ok|not good|still not okay|still not ok)\b/i,
  /\b(?:still want to|still going to|about to|gonna)\b.{0,60}\b(?:kill|die|hurt|cut|suicide|end my life)\b/i,
  /\b(?:knife|gun|blade|razor|pills|rope)\b.{0,80}\b(?:with me|in my hand|near me|still have|kill|hurt|cut|suicide)\b/i,
]

const SAFE_PATTERNS = [
  /^\s*(?:safe|im safe|i am safe|i'm safe|safe now|im good|i'm good|i am good|im okay|i'm okay|i am okay|im ok|i'm ok|i am ok|okay now|ok now|fine now|alright now)\s*[.!]*\s*$/i,
  /\b(?:i\s*(?:am|'m)|im)\s+(?:safe|okay|ok|good|fine|alright)\b/i,
  /\b(?:safe now|not in danger|no danger|out of danger|away from danger)\b/i,
  /\b(?:i put|ive put|i've put|i moved|ive moved|i've moved)\b.{0,50}\b(?:knife|gun|blade|razor|pills|rope|it|them)\b.{0,30}\b(?:away|down|outside)\b/i,
]

export function classifyPostCrisisSafetyReply(message: string): CrisisSafetyStatus {
  const text = message.trim()
  if (!text) return 'unknown'
  if (DANGER_PATTERNS.some((pattern) => pattern.test(text))) return 'danger'
  if (SAFE_PATTERNS.some((pattern) => pattern.test(text))) return 'safe'
  return 'unknown'
}

export function postCrisisSafetyStorageKey(userId: string) {
  return `sentimind-post-crisis-safety:${userId}`
}

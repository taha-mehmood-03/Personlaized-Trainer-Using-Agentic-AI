const EMPTY_LABELS = new Set(['', '0', 'none', 'null', 'undefined', 'nan', 'n/a', 'unknown'])
const NUMERIC_PLACEHOLDER = /^[-+]?(?:\d+|\d*\.\d+)$/
const ASSISTANT_NUMERIC_PREFIX = /^(?:0(?:\.\d+)?|1\.0+)$/

export function cleanEmotionLabel(value: unknown): string | null {
  if (typeof value !== 'string') return null

  const raw = value.trim()
  if (!raw) return null

  const enumValue = raw.includes('.') ? raw.split('.').pop()?.trim() ?? raw : raw
  const lower = enumValue.toLowerCase()

  if (EMPTY_LABELS.has(lower) || NUMERIC_PLACEHOLDER.test(lower)) return null

  const label = enumValue.replace(/_/g, ' ')
  return /^[A-Z ]+$/.test(label) ? label.toLowerCase() : label
}

export function firstEmotionLabel(...values: unknown[]): string | null {
  for (const value of values) {
    const clean = cleanEmotionLabel(value)
    if (clean) return clean
  }
  return null
}

export function cleanEmotionList(value: unknown): string[] {
  if (!Array.isArray(value)) return []

  return value
    .map((item) => cleanEmotionLabel(item))
    .filter((item): item is string => Boolean(item))
}

export function cleanAssistantContent(content: unknown, role: 'user' | 'assistant' = 'assistant'): string {
  const text = typeof content === 'string' ? content : ''
  if (role === 'user') return text

  const withoutNumericLine = text.replace(/^\s*(?:0(?:\.\d+)?|1\.0+)\s*(?:\r?\n)+/, '')
  const withoutInlinePrefix = withoutNumericLine.replace(/^\s*(?:0(?:\.\d+)?|1\.0+)\s+(?=[A-Za-z"'])/, '')

  return ASSISTANT_NUMERIC_PREFIX.test(withoutInlinePrefix.trim()) ? '' : withoutInlinePrefix
}

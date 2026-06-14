import { devError, devLog, devWarn } from '@/lib/logger'

interface CrisisLocationOptions {
  apiBase: string
  userId: string
  crisisLevel?: 'high'
}

const HIGH_RISK_GPS_PATTERNS = [
  /\b(?:i\s*(?:am|'m|will|want|might|may)|im)\b.{0,80}\b(?:kill myself|end my life|hurt myself|cut myself|suicide)\b/i,
  /\b(?:kill myself|end my life|hurt myself|cut myself|suicide)\b/i,
  /\b(?:knife|gun|blade|razor|pills|rope)\b.{0,80}\b(?:kill|die|end|hurt|cut|suicide)\b/i,
  /\b(?:going to|gonna|about to|will)\b.{0,40}\b(?:kill|hurt|cut)\b/i,
]

export function shouldRequestCrisisGps(message: string) {
  const text = message.trim()
  return Boolean(text && HIGH_RISK_GPS_PATTERNS.some((pattern) => pattern.test(text)))
}

async function sendPreciseLocation({
  apiBase,
  userId,
  latitude,
  longitude,
  accuracy,
  crisisLevel = 'high',
}: CrisisLocationOptions & {
  latitude: number
  longitude: number
  accuracy: number
}): Promise<boolean> {
  const response = await fetch(`${apiBase}/crisis/send-location`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-SentiMind-User-Id': userId,
    },
    body: JSON.stringify({
      user_id: userId,
      latitude,
      longitude,
      accuracy,
      crisis_level: crisisLevel,
    }),
  })

  const data = await response.json().catch(() => null)
  if (data?.success) {
    devLog('[CRISIS] Precise browser location sent to emergency contact channel.')
    return true
  } else {
    devWarn('[CRISIS] Failed to send precise browser location:', data?.error)
    return false
  }
}

export function sendCrisisLocation(options: CrisisLocationOptions): Promise<boolean> {
  if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
    devWarn('[CRISIS] Geolocation is not available in this browser context.')
    return Promise.resolve(false)
  }

  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude, accuracy } = position.coords
        void sendPreciseLocation({
          ...options,
          latitude,
          longitude,
          accuracy,
        })
          .then(resolve)
          .catch((error) => {
            devError('[CRISIS] Error sending precise browser location:', error)
            resolve(false)
          })
      },
      (error) => {
        devWarn('[CRISIS] Browser GPS unavailable or denied; IP fallback is disabled:', error.code)
        resolve(false)
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0,
      }
    )
  })
}

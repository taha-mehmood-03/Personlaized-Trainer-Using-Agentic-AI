'use client'

import { AlertTriangle, ExternalLink } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, CrisisResource } from '@/lib/api'

// ─── Crisis Banner Component ──────────────────────────────────────────────────
export function CrisisBanner() {
  const [resources, setResources] = useState<CrisisResource | null>(null)
  const [countryCode, setCountryCode] = useState<string>('US')

  useEffect(() => {
    const loadResources = async () => {
      try {
        // Detect country
        const detectResult = await api.post<any>('/crisis/detect-country', {
          user_data: {}
        })
        
        const country = detectResult.data?.country_code || 'US'
        setCountryCode(country)

        // Load resources for country
        const resourceResult = await api.post<CrisisResource>('/crisis/resources', {
          country_code: country
        })
        
        if (resourceResult.ok && resourceResult.data) {
          setResources(resourceResult.data)
        }
      } catch (err) {
        console.error('Error loading crisis banner resources:', err)
        // Fallback to default resources
        setResources({
          primary_hotline: {
            name: '988 Suicide & Crisis Lifeline',
            number: '988',
            available: '24/7'
          }
        })
      }
    }

    loadResources()
  }, [])

  // Get resource link based on country
  const getResourceLink = () => {
    switch (countryCode) {
      case 'PK':
        return 'https://www.iasp.info/resources/Crisis_Centres/'
      case 'GB':
        return 'https://www.samaritans.org/'
      case 'AU':
        return 'https://www.lifeline.org.au/'
      default:
        return 'https://988lifeline.org/find-a-crisis-center/'
    }
  }

  const hotline = resources?.primary_hotline?.number || '988'

  return (
    <div className="w-full bg-red-600 text-white px-4 py-2.5 flex items-center justify-center gap-3 text-sm font-medium z-50 shrink-0 flex-wrap">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      <span>
        Feeling in crisis? Please reach out for immediate help.{' '}
        <strong>{resources?.primary_hotline?.call_text || 'Call'}</strong>{' '}
        <strong>{hotline}</strong>{' '}
        anytime{countryCode === 'PK' ? ' in Pakistan' : countryCode === 'GB' ? ' in UK' : countryCode === 'AU' ? ' in Australia' : ' in the US & Canada'}.
      </span>
      <a
        href={getResourceLink()}
        target="_blank"
        rel="noopener noreferrer"
        className="underline font-bold flex items-center gap-1 hover:text-red-100 transition-colors whitespace-nowrap"
      >
        Find Local Resources
        <ExternalLink className="w-3.5 h-3.5" />
      </a>
    </div>
  )
}

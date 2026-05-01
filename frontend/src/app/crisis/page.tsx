'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Phone, ShieldAlert, Loader } from 'lucide-react'
import { api, CrisisResource, CrisisCallResponse } from '@/lib/api'

export default function CrisisPage() {
  const [resources, setResources] = useState<CrisisResource | null>(null)
  const [countryCode, setCountryCode] = useState<string>('US')
  const [loading, setLoading] = useState(true)
  const [calling, setCalling] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch crisis resources on mount
  useEffect(() => {
    const fetchResources = async () => {
      try {
        setLoading(true)
        
        // First, try to detect user's country
        const detectResult = await api.post<any>('/crisis/detect-country', {
          user_data: {}
        })
        
        if (detectResult.ok && detectResult.data?.country_code) {
          setCountryCode(detectResult.data.country_code)
        }
        
        // Then fetch resources for detected country
        const country = detectResult.data?.country_code || 'US'
        const resourceResult = await api.post<CrisisResource>('/crisis/resources', {
          country_code: country,
          user_id: 'anonymous'
        })
        
        if (resourceResult.ok && resourceResult.data) {
          setResources(resourceResult.data)
        } else {
          throw new Error('Failed to fetch crisis resources')
        }
      } catch (err) {
        console.error('Error fetching resources:', err)
        setError('Unable to load crisis resources')
        // Fallback to US resources
        setResources({
          primary_hotline: {
            name: '988 Suicide & Crisis Lifeline',
            number: '988',
            available: '24/7',
            call_text: 'Call or text'
          },
          text_line: {
            name: 'Crisis Text Line',
            action: 'Text HOME to 741741',
            available: '24/7',
            supported: true
          }
        })
      } finally {
        setLoading(false)
      }
    }

    fetchResources()
  }, [])

  const handleDirectCall = async () => {
    try {
      setCalling(true)
      setError(null)

      const hotline = resources?.primary_hotline?.number || '988'
      
      // Try to initiate Twilio call if phone is available
      // For now, fall back to tel: protocol
      const phoneFormatted = hotline.replace(/[^0-9+]/g, '')
      window.location.href = `tel:${phoneFormatted}`
    } catch (err) {
      console.error('Error initiating call:', err)
      setError('Unable to initiate direct call. Please dial manually.')
    } finally {
      setCalling(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-rose-50 flex flex-col items-center justify-center p-4">
        <div className="max-w-xl w-full bg-white rounded-3xl shadow-lg border-2 border-rose-100 p-8 text-center space-y-8">
          <Loader className="w-10 h-10 animate-spin mx-auto text-rose-600" />
          <p className="text-slate-600">Loading crisis resources...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-rose-50 flex flex-col items-center justify-center p-4">
      <div className="max-w-xl w-full bg-white rounded-3xl shadow-lg border-2 border-rose-100 p-8 text-center space-y-8">
        <div className="w-20 h-20 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center mx-auto mb-2">
          <ShieldAlert className="w-10 h-10" />
        </div>
        
        <div>
          <h1 className="text-3xl font-black text-slate-900 mb-4">You Are Not Alone.</h1>
          <p className="text-lg text-slate-600 leading-relaxed font-medium">
            We noticed you might be going through a particularly difficult time right now. SentiMind is not equipped for medical emergencies or crisis intervention.
            <br/><br/>
            Please reach out to a professional immediately. There are people who want to help you right now.
          </p>
          {error && (
            <p className="text-sm text-red-600 mt-4 bg-red-50 p-2 rounded">{error}</p>
          )}
        </div>

        <div className="space-y-4">
          {/* Primary Hotline */}
          {resources?.primary_hotline && (
            <div>
              <Button 
                onClick={handleDirectCall}
                disabled={calling}
                size="lg" 
                className="w-full bg-rose-600 hover:bg-rose-700 text-white h-16 text-lg rounded-2xl shadow-rose-200 shadow-xl border-none disabled:opacity-50"
              >
                <Phone className="w-5 h-5 mr-3" />
                {calling ? 'Connecting...' : `Call ${resources.primary_hotline.name}`}
              </Button>
              <p className="text-xs text-slate-500 mt-2">
                {resources.primary_hotline.number} • Available {resources.primary_hotline.available}
              </p>
              {resources.primary_hotline.language && (
                <p className="text-xs text-slate-500">Language: {resources.primary_hotline.language}</p>
              )}
            </div>
          )}

          {/* Secondary Hotline (for Pakistan) */}
          {resources?.secondary_hotline && (
            <div>
              <Button asChild variant="outline" size="lg" className="w-full h-14 text-base rounded-xl border-slate-300">
                <a href={`tel:${resources.secondary_hotline.number.replace(/[^0-9+]/g, '')}`}>
                  <Phone className="w-4 h-4 mr-2" />
                  {resources.secondary_hotline.name}
                </a>
              </Button>
              <p className="text-xs text-slate-500 mt-2">
                {resources.secondary_hotline.number} • Available {resources.secondary_hotline.available}
              </p>
            </div>
          )}

          {/* Text Line */}
          {resources?.text_line?.supported && (
            <Button asChild variant="outline" size="lg" className="w-full h-14 text-base rounded-xl border-slate-300">
              <a href={resources.text_line.action.includes('WhatsApp') ? 
                `https://wa.me/${resources.text_line.action.match(/\+\d+/)?.[0]}` :
                `sms:${resources.text_line.action.split(' ').pop()}`
              }>
                {resources.text_line.action}
              </a>
            </Button>
          )}

          {/* Tertiary Hotline */}
          {resources?.tertiary_hotline && (
            <Button asChild variant="outline" size="lg" className="w-full h-14 text-sm rounded-xl border-slate-300">
              <a href={`tel:${resources.tertiary_hotline.number.replace(/[^0-9+]/g, '')}`}>
                <Phone className="w-4 h-4 mr-2" />
                {resources.tertiary_hotline.name}
              </a>
            </Button>
          )}
        </div>

        {resources?.message && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm text-blue-900">{resources.message}</p>
          </div>
        )}

        <div className="pt-8 border-t border-slate-100">
          <Button asChild variant="ghost" className="text-slate-500">
            <Link href="/chat">Return to Chat</Link>
          </Button>
        </div>
      </div>
    </div>
  )
}

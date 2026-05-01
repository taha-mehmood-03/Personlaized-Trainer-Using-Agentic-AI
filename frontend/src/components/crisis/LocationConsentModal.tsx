'use client'

import React, { useState, useEffect } from 'react'
import { MapPin, ShieldAlert, CheckCircle2, AlertTriangle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface LocationConsentModalProps {
  onComplete: () => void
}

export function LocationConsentModal({ onComplete }: LocationConsentModalProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Check if we've already asked for consent in this session or if it's already granted
  useEffect(() => {
    const hasConsented = sessionStorage.getItem('location_consent_resolved')
    if (!hasConsented) {
      setIsOpen(true)
    } else {
      onComplete()
    }
  }, [onComplete])

  const requestLocation = () => {
    setLoading(true)
    setError(null)
    
    if (!('geolocation' in navigator)) {
      setError('Location services are not supported by your browser.')
      setLoading(false)
      return
    }

    // This triggers the native browser prompt since we are asking for precise location
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        console.log('[LOCATION-MODAL] ✅ GPS permission granted', pos.coords)
        sessionStorage.setItem('location_consent_resolved', 'granted')
        setLoading(false)
        setIsOpen(false)
        onComplete()
      },
      (err) => {
        console.warn('[LOCATION-MODAL] 📍 GPS permission denied or failed:', err.message)
        // If it's permission denied (they blocked it or it's blocked by OS)
        if (err.code === err.PERMISSION_DENIED) {
          setError('Location is currently blocked by your browser. Please click the lock/location icon in your URL bar, change to "Allow", and try again. Or click "Skip for now".')
        } else {
          setError(`Failed to get location: ${err.message}`)
        }
        setLoading(false)
        // Don't close the modal automatically so they can see the error!
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    )
  }

  const handleSkip = () => {
    sessionStorage.setItem('location_consent_resolved', 'skipped')
    setIsOpen(false)
    onComplete()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden animate-in fade-in zoom-in duration-300">
        <div className="bg-rose-50 p-6 flex flex-col items-center text-center border-b border-rose-100">
          <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center shadow-inner mb-4">
            <ShieldAlert className="w-8 h-8 text-rose-500" />
          </div>
          <h2 className="text-2xl font-bold text-slate-800">Emergency Support</h2>
          <p className="text-rose-600 font-medium mt-1">Your safety is our priority</p>
        </div>
        
        <div className="p-6 space-y-6">
          <p className="text-slate-600 text-center leading-relaxed">
            SentiMind uses your precise location <span className="font-semibold text-slate-800">only during mental health crises</span>. 
            If our AI detects a severe emergency, we use this to dispatch automated crisis alerts to your trusted contacts, ensuring help can reach you immediately.
          </p>

          <div className="bg-slate-50 rounded-xl p-4 space-y-3">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />
              <p className="text-sm text-slate-700">Used strictly for emergency WhatsApp alerts</p>
            </div>
            <div className="flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />
              <p className="text-sm text-slate-700">Never shared with third-party advertisers</p>
            </div>
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-sm text-slate-700">You may receive a browser prompt after clicking "Enable"</p>
            </div>
          </div>

          {error && (
            <div className="text-sm text-rose-600 bg-rose-50 p-3 rounded-lg border border-rose-100 text-center">
              {error}
            </div>
          )}

          <div className="space-y-3 pt-2">
            <Button 
              onClick={requestLocation} 
              disabled={loading}
              className="w-full bg-rose-500 hover:bg-rose-600 text-white py-6 rounded-xl text-lg font-semibold shadow-lg shadow-rose-500/30 transition-all flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Requesting Permission...
                </>
              ) : (
                <>
                  <MapPin className="w-5 h-5" />
                  Enable Precise Location
                </>
              )}
            </Button>
            
            <button 
              onClick={handleSkip}
              disabled={loading}
              className="w-full py-3 text-sm font-medium text-slate-500 hover:text-slate-800 transition-colors"
            >
              Skip for now
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

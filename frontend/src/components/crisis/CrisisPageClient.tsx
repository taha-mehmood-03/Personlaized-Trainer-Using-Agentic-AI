import React from 'react'
import Link from 'next/link'
import { Phone, ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { CrisisResource } from '@/lib/api'
import { BreathingGuide } from '@/components/crisis/BreathingGuide'

interface CrisisPageClientProps {
  resources: CrisisResource
  countryCode: string
  initialError?: string | null
}

function phoneHref(number: string): string {
  return number.replace(/[^0-9+]/g, '')
}

function whatsappHref(action: string): string {
  const match = action.match(/\+[\d-]+/)
  const number = match?.[0]?.replace(/[^0-9]/g, '')
  return number ? `https://wa.me/${number}` : '#'
}

export function CrisisPageClient({
  resources,
  countryCode,
  initialError = null,
}: CrisisPageClientProps) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-rose-50 p-4">
      <div className="w-full max-w-xl space-y-8 rounded-3xl border-2 border-rose-100 bg-white p-8 text-center shadow-lg">
        <div className="mx-auto mb-2 flex h-20 w-20 items-center justify-center rounded-full bg-rose-100 text-rose-600">
          <ShieldAlert className="h-10 w-10" />
        </div>

        <div>
          <h1 className="mb-4 text-3xl font-black text-slate-900">You Are Not Alone.</h1>
          <p className="mb-3 text-xs font-bold uppercase tracking-widest text-rose-500">
            Crisis resources for {countryCode}
          </p>
          <p className="text-lg font-medium leading-relaxed text-slate-600">
            We noticed you might be going through a particularly difficult time right now. SentiMind is not equipped for medical emergencies or crisis intervention.
            <br />
            <br />
            Please reach out to a professional immediately. There are people who want to help you right now.
          </p>
          {initialError && (
            <p className="mt-4 rounded bg-red-50 p-2 text-sm text-red-600">{initialError}</p>
          )}
        </div>

        <div className="space-y-4">
          {resources?.primary_hotline && (
            <div>
              <Button
                asChild
                size="lg"
                className="h-16 w-full rounded-2xl border-none bg-rose-600 text-lg text-white shadow-xl shadow-rose-200 hover:bg-rose-700"
              >
                <a href={`tel:${phoneHref(resources.primary_hotline.number)}`}>
                  <Phone className="mr-3 h-5 w-5" />
                  Call {resources.primary_hotline.name}
                </a>
              </Button>
              <p className="mt-2 text-xs text-slate-500">
                {resources.primary_hotline.number} - Available {resources.primary_hotline.available}
              </p>
              {resources.primary_hotline.language && (
                <p className="text-xs text-slate-500">Language: {resources.primary_hotline.language}</p>
              )}
            </div>
          )}

          {resources?.secondary_hotline && (
            <div>
              <Button asChild variant="outline" size="lg" className="h-14 w-full rounded-xl border-slate-300 text-base">
                <a href={`tel:${phoneHref(resources.secondary_hotline.number)}`}>
                  <Phone className="mr-2 h-4 w-4" />
                  {resources.secondary_hotline.name}
                </a>
              </Button>
              <p className="mt-2 text-xs text-slate-500">
                {resources.secondary_hotline.number} - Available {resources.secondary_hotline.available}
              </p>
            </div>
          )}

          {resources?.text_line?.supported && (
            <Button asChild variant="outline" size="lg" className="h-14 w-full rounded-xl border-slate-300 text-base">
              <a href={resources.text_line.action.includes('WhatsApp')
                ? whatsappHref(resources.text_line.action)
                : `sms:${resources.text_line.action.split(' ').pop()}`
              }>
                {resources.text_line.action}
              </a>
            </Button>
          )}

          {resources?.tertiary_hotline && (
            <Button asChild variant="outline" size="lg" className="h-14 w-full rounded-xl border-slate-300 text-sm">
              <a href={`tel:${phoneHref(resources.tertiary_hotline.number)}`}>
                <Phone className="mr-2 h-4 w-4" />
                {resources.tertiary_hotline.name}
              </a>
            </Button>
          )}

          {resources?.emergency_service && (
            <Button asChild variant="outline" size="lg" className="h-14 w-full rounded-xl border-slate-300 text-sm">
              <a href={`tel:${phoneHref(resources.emergency_service.number)}`}>
                <Phone className="mr-2 h-4 w-4" />
                {resources.emergency_service.name}
              </a>
            </Button>
          )}
        </div>

        {resources?.message && (
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
            <p className="text-sm text-blue-900">{resources.message}</p>
          </div>
        )}

        <div className="border-t border-slate-100 pt-6">
          <p className="mb-4 text-center text-xs font-bold uppercase tracking-widest text-slate-500">
            Breathing First Aid
          </p>
          <BreathingGuide />
        </div>

        <div className="flex flex-wrap justify-center gap-2">
          {[
            'This feeling is temporary',
            'Help is available right now',
            'Your safety matters deeply',
          ].map((message) => (
            <span
              key={message}
              className="rounded-full border border-rose-100 bg-rose-50 px-4 py-2 text-xs font-semibold text-rose-700"
            >
              {message}
            </span>
          ))}
        </div>

        <div className="border-t border-slate-100 pt-4">
          <Button asChild variant="ghost" className="text-slate-500">
            <Link href="/chat">Return to Chat</Link>
          </Button>
        </div>
      </div>
    </div>
  )
}

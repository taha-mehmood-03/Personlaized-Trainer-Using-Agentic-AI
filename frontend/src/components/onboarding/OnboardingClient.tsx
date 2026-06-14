'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { BellRing, CheckCircle2, Loader2, LockKeyhole, MapPin, MessageSquareText, Mic, Phone, Plus, Trash2, Users } from 'lucide-react'
import { OnboardingStep } from '@/components/onboarding/OnboardingStep'
import { MoodPicker } from '@/components/onboarding/MoodPicker'
import { GoalSelector } from '@/components/onboarding/GoalSelector'
import { ToggleSetting } from '@/components/profile/ToggleSetting'
import { saveOnboarding } from '@/actions/onboarding'
import { EmergencyContactInput, MoodLevel, OnboardingData } from '@/types'

const STEP_SUPPORT = {
    mood: [
        { label: 'Used for', value: 'baseline' },
        { label: 'Dashboard', value: 'day one' },
        { label: 'Crisis path', value: 'unchanged' },
    ],
    goals: [
        { label: 'Select', value: '1 or more' },
        { label: 'Personalizes', value: 'routing' },
        { label: 'Updates', value: 'profile' },
    ],
    reminders: [
        { label: 'Optional', value: 'yes' },
        { label: 'Default', value: 'daily' },
        { label: 'Next', value: 'safety' },
    ],
    safety: [
        { label: 'Location', value: 'crisis only' },
        { label: 'Contacts', value: 'trusted' },
        { label: 'Twilio', value: 'alerts' },
    ],
}

interface OnboardingClientProps {
    userId: string
}

export function OnboardingClient({ userId }: OnboardingClientProps) {
    const router = useRouter()

    const [step, setStep] = useState(1)
    const [data, setData] = useState<OnboardingData>({
        mood: null,
        goals: [],
        notificationsEnabled: true,
        crisisLocationConsent: false,
        emergencyContactConsent: false,
        emergencyContacts: [],
        voiceAnalysisConsent: false, // GAP-07: default off — must be explicit opt-in
    })
    const [contactDraft, setContactDraft] = useState<EmergencyContactInput>({
        name: '',
        phone: '',
        relation: '',
        channel: 'sms',
    })
    const [locationLoading, setLocationLoading] = useState(false)
    const [locationError, setLocationError] = useState<string | null>(null)
    const [saving, setSaving] = useState(false)

    const addContact = (contact: EmergencyContactInput) => {
        const name = contact.name.trim()
        const phone = contact.phone.trim()
        if (!name || !phone) return
        setData((current) => ({
            ...current,
            emergencyContactConsent: true,
            emergencyContacts: [
                ...current.emergencyContacts.filter((item) => item.phone.trim() !== phone),
                {
                    name,
                    phone,
                    relation: contact.relation?.trim() || undefined,
                    channel: contact.channel ?? 'sms',
                },
            ],
        }))
    }

    const requestLocationAccess = () => {
        setLocationError(null)
        if (!('geolocation' in navigator)) {
            setLocationError('Location is not supported in this browser.')
            return
        }
        setLocationLoading(true)
        navigator.geolocation.getCurrentPosition(
            () => {
                setData((current) => ({ ...current, crisisLocationConsent: true }))
                setLocationLoading(false)
            },
            (err) => {
                setLocationError(err.code === err.PERMISSION_DENIED
                    ? 'Location is blocked. Allow it from the browser address-bar permissions, then try again.'
                    : `Location request failed: ${err.message}`)
                setLocationLoading(false)
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        )
    }

    const pickContacts = async () => {
        const contactsApi = (navigator as Navigator & {
            contacts?: {
                select: (
                    fields: string[],
                    options?: { multiple?: boolean }
                ) => Promise<Array<{ name?: string[]; tel?: string[] }>>
            }
        }).contacts

        if (!contactsApi?.select) {
            setLocationError('Contact sharing is not supported in this browser. Add a trusted contact manually.')
            return
        }

        try {
            const contacts = await contactsApi.select(['name', 'tel'], { multiple: true })
            contacts.forEach((contact) => {
                addContact({
                    name: contact.name?.[0] ?? 'Trusted contact',
                    phone: contact.tel?.[0] ?? '',
                    channel: 'sms',
                })
            })
        } catch {
            setLocationError('Contact sharing was cancelled or blocked. Manual entry still works.')
        }
    }

    const handleFinish = async () => {
        setSaving(true)
        try {
            await saveOnboarding(userId, data)
        } catch {
            // Onboarding should never trap the user if the profile write is unavailable.
        } finally {
            setSaving(false)
            router.push('/chat')
        }
    }

    if (step === 1) {
        return (
            <OnboardingStep
                step={1}
                totalSteps={4}
                title="How are you feeling lately?"
                subtitle="This gives the dashboard a starting point without forcing the chat to diagnose you."
                onNext={() => setStep(2)}
                nextDisabled={!data.mood}
                supportingItems={STEP_SUPPORT.mood}
            >
                <MoodPicker
                    selected={data.mood}
                    onChange={(mood: MoodLevel) => setData((current) => ({ ...current, mood }))}
                />
            </OnboardingStep>
        )
    }

    if (step === 2) {
        return (
            <OnboardingStep
                step={2}
                totalSteps={4}
                title="What should SentiMind pay attention to?"
                subtitle="Choose the areas you want support around. You can change these later as the system learns from feedback."
                onBack={() => setStep(1)}
                onNext={() => setStep(3)}
                nextDisabled={data.goals.length === 0}
                supportingItems={STEP_SUPPORT.goals}
            >
                <GoalSelector
                    selected={data.goals}
                    onChange={(goals) => setData((current) => ({ ...current, goals }))}
                />
            </OnboardingStep>
        )
    }

    if (step === 3) {
        return (
            <OnboardingStep
                step={3}
                totalSteps={4}
                title="Set your check-in rhythm"
                subtitle="Reminders are optional. The important part is that your sessions stay connected over time."
                onBack={() => setStep(2)}
                onNext={() => setStep(4)}
                supportingItems={STEP_SUPPORT.reminders}
            >
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                    <div className="mb-4 flex items-start gap-3 rounded-2xl bg-white p-4">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-cyan-50 text-cyan-700">
                            <BellRing className="h-5 w-5" />
                        </div>
                        <div>
                            <p className="text-sm font-black text-slate-950">Daily check-in</p>
                            <p className="mt-1 text-xs leading-5 text-slate-500">
                                A small reminder helps long-term trends become more reliable.
                            </p>
                        </div>
                    </div>
                    <ToggleSetting
                        label="Daily Check-in Reminders"
                        description="Get a gentle nudge to reflect each day"
                        checked={data.notificationsEnabled}
                        onChange={(value) => setData((current) => ({ ...current, notificationsEnabled: value }))}
                    />
                </div>

                {/* GAP-07: Voice analysis consent — separate opt-in required (GDPR Art. 9) */}
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 mt-3">
                    <div className="mb-4 flex items-start gap-3 rounded-2xl bg-white p-4">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-cyan-50 text-cyan-700">
                            <Mic className="h-5 w-5" />
                        </div>
                        <div>
                            <p className="text-sm font-black text-slate-950">
                                Voice tone analysis
                                <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500">Optional</span>
                            </p>
                            <p className="mt-1 text-xs leading-5 text-slate-500">
                                Analyses acoustic features in your voice to detect emotional tone.
                                Raw audio is never stored. You can withdraw this at any time in Profile settings.
                            </p>
                        </div>
                    </div>
                    <ToggleSetting
                        label="Enable voice tone analysis"
                        description="Opt in to allow acoustic emotion detection"
                        checked={data.voiceAnalysisConsent}
                        onChange={(value) => setData((current) => ({ ...current, voiceAnalysisConsent: value }))}
                    />
                </div>

                <div className="grid gap-2 pt-2 sm:grid-cols-3">
                    {[
                        { icon: LockKeyhole, label: 'Private setup' },
                        { icon: MessageSquareText, label: 'Context preserved' },
                        { icon: CheckCircle2, label: 'Editable later' },
                    ].map(({ icon: Icon, label }) => (
                        <div key={label} className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
                            <Icon className="h-4 w-4 text-slate-500" />
                            <span className="text-xs font-bold text-slate-600">{label}</span>
                        </div>
                    ))}
                </div>
            </OnboardingStep>
        )
    }

    const canFinish = data.crisisLocationConsent && data.emergencyContacts.length > 0 && !saving

    return (
        <OnboardingStep
            step={4}
            totalSteps={4}
            title="Choose crisis contacts"
            subtitle="If SentiMind detects a severe emergency, Twilio can alert your trusted contacts with your current location."
            onBack={() => setStep(3)}
            onNext={handleFinish}
            nextLabel={saving ? 'Setting up...' : 'Start Chatting'}
            nextDisabled={!canFinish}
            supportingItems={STEP_SUPPORT.safety}
        >
            <div className="space-y-4">
                <div className="rounded-2xl border border-rose-100 bg-rose-50 p-4">
                    <div className="flex items-start gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-rose-600">
                            <MapPin className="h-5 w-5" />
                        </div>
                        <div className="flex-1">
                            <p className="text-sm font-black text-slate-950">Crisis location access</p>
                            <p className="mt-1 text-xs leading-5 text-slate-600">
                                The browser permission is requested once now. During a crisis alert, the app asks the browser for your current GPS position and sends it only to your trusted contacts.
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={requestLocationAccess}
                            disabled={locationLoading || data.crisisLocationConsent}
                            className="inline-flex h-10 items-center gap-2 rounded-xl bg-slate-950 px-3 text-xs font-bold text-white disabled:bg-emerald-600"
                        >
                            {locationLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPin className="h-4 w-4" />}
                            {data.crisisLocationConsent ? 'Allowed' : 'Allow'}
                        </button>
                    </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="mb-4 flex items-start justify-between gap-3">
                        <div className="flex items-start gap-3">
                            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-slate-700">
                                <Users className="h-5 w-5" />
                            </div>
                            <div>
                                <p className="text-sm font-black text-slate-950">Trusted emergency contacts</p>
                                <p className="mt-1 text-xs leading-5 text-slate-600">
                                    These numbers receive Twilio crisis alerts and location links.
                                </p>
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={pickContacts}
                            className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700"
                        >
                            <Phone className="h-4 w-4" />
                            Share
                        </button>
                    </div>

                    <div className="grid gap-2 sm:grid-cols-[1fr_1fr_0.75fr_auto]">
                        <input
                            value={contactDraft.name}
                            onChange={(event) => setContactDraft((current) => ({ ...current, name: event.target.value }))}
                            placeholder="Name"
                            className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
                        />
                        <input
                            value={contactDraft.phone}
                            onChange={(event) => setContactDraft((current) => ({ ...current, phone: event.target.value }))}
                            placeholder="+923001234567"
                            className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
                        />
                        <select
                            value={contactDraft.channel}
                            onChange={(event) => setContactDraft((current) => ({ ...current, channel: event.target.value as 'sms' | 'whatsapp' }))}
                            className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
                        >
                            <option value="sms">SMS</option>
                            <option value="whatsapp">WhatsApp</option>
                        </select>
                        <button
                            type="button"
                            onClick={() => {
                                addContact(contactDraft)
                                setContactDraft({ name: '', phone: '', relation: '', channel: 'sms' })
                            }}
                            className="inline-flex h-11 items-center justify-center rounded-xl bg-slate-950 px-4 text-white"
                        >
                            <Plus className="h-4 w-4" />
                        </button>
                    </div>

                    <div className="mt-4 space-y-2">
                        {data.emergencyContacts.map((contact) => (
                            <div key={contact.phone} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2">
                                <div className="min-w-0">
                                    <p className="truncate text-sm font-bold text-slate-900">{contact.name}</p>
                                    <p className="text-xs text-slate-500">{contact.phone} - {contact.channel?.toUpperCase() ?? 'SMS'}</p>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => setData((current) => ({
                                        ...current,
                                        emergencyContacts: current.emergencyContacts.filter((item) => item.phone !== contact.phone),
                                    }))}
                                    className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-rose-600"
                                >
                                    <Trash2 className="h-4 w-4" />
                                </button>
                            </div>
                        ))}
                    </div>
                </div>

                {locationError && (
                    <div className="rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
                        {locationError}
                    </div>
                )}
            </div>
        </OnboardingStep>
    )
}

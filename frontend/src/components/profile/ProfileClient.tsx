'use client'

import React, { useState, useCallback, useEffect } from 'react'
import { Navbar } from '@/components/layout/Navbar'
import { SettingsTab } from '@/components/profile/SettingsTab'
import { ToggleSetting } from '@/components/profile/ToggleSetting'
import { DangerZone } from '@/components/profile/DangerZone'
import { signOut } from 'next-auth/react'
import {
    exportUserData,
    getUserProfile,
    requestAccountErasure,
    saveUserSettings,
    withdrawUserConsent,
} from '@/actions/profile'
import { UserProfile, UserSettings } from '@/types'
import {
    Ban,
    Download,
    User,
    Sliders,
    Shield,
    Phone,
    Palette,
    Info,
    LogOut,
    CheckCircle,
    Loader,
    Monitor,
    Moon,
    Sun,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { applyThemePreference, ThemePreference } from '@/components/theme/ThemeProvider'

type TabId = 'account' | 'preferences' | 'privacy' | 'crisis' | 'appearance' | 'about'

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'account', label: 'Account', icon: <User className="w-4 h-4" /> },
    { id: 'preferences', label: 'Preferences', icon: <Sliders className="w-4 h-4" /> },
    { id: 'privacy', label: 'Privacy', icon: <Shield className="w-4 h-4" /> },
    { id: 'crisis', label: 'Crisis', icon: <Phone className="w-4 h-4" /> },
    { id: 'appearance', label: 'Appearance', icon: <Palette className="w-4 h-4" /> },
    { id: 'about', label: 'About', icon: <Info className="w-4 h-4" /> },
]

const THEME_OPTIONS = [
    { value: 'light' as const, label: 'Light', icon: Sun },
    { value: 'dark' as const, label: 'Dark', icon: Moon },
    { value: 'system' as const, label: 'System', icon: Monitor },
]

const DEFAULT_SETTINGS: UserSettings = {
    dailyReminderEnabled: true,
    weeklyEmailEnabled: true,
    sessionAutoSave: true,
    anonymousMode: false,
    shareLocationInCrisis: false,
    emergencyContactConsent: false,
    voiceAnalysisConsent: false,
    theme: 'light',
}

interface ProfileClientProps {
    userId: string
    profile: UserProfile | null
    fallbackName?: string | null
    fallbackEmail?: string | null
}

export function ProfileClient({
    userId,
    profile,
    fallbackName,
    fallbackEmail,
}: ProfileClientProps) {
    const [activeTab, setActiveTab] = useState<TabId>('account')
    const [saved, setSaved] = useState(false)
    const [saving, setSaving] = useState(false)
    const [saveError, setSaveError] = useState('')
    const [privacyMessage, setPrivacyMessage] = useState('')
    const [exporting, setExporting] = useState(false)
    const [withdrawingConsent, setWithdrawingConsent] = useState(false)
    const [profileLoading, setProfileLoading] = useState(false)
    const [loadedProfile, setLoadedProfile] = useState(Boolean(profile))
    const [displayName, setDisplayName] = useState(profile?.name || fallbackName || '')
    const [displayEmail, setDisplayEmail] = useState(profile?.email || fallbackEmail || '')
    const [settings, setSettings] = useState<UserSettings>({
        ...DEFAULT_SETTINGS,
        ...(profile?.settings ?? {}),
    })

    const loadProfile = useCallback(async () => {
        if (!userId || loadedProfile || profileLoading) return
        setProfileLoading(true)
        getUserProfile(userId)
            .then((nextProfile) => {
                if (!nextProfile) return
                setDisplayName(nextProfile.name || fallbackName || '')
                setDisplayEmail(nextProfile.email || fallbackEmail || '')
                setSettings({
                    ...DEFAULT_SETTINGS,
                    ...(nextProfile.settings ?? {}),
                })
                if (nextProfile.settings?.theme) {
                    applyThemePreference(nextProfile.settings.theme)
                }
                setLoadedProfile(true)
            })
            .finally(() => {
                setProfileLoading(false)
            })
    }, [fallbackEmail, fallbackName, loadedProfile, profileLoading, userId])

    useEffect(() => {
        if (activeTab !== 'account' && activeTab !== 'about') {
            loadProfile()
        }
    }, [activeTab, loadProfile])

    useEffect(() => {
        if (profile?.settings?.theme) {
            applyThemePreference(profile.settings.theme)
        }
    }, [profile?.settings?.theme])

    const toggle = (key: keyof UserSettings) => (val: boolean) =>
        setSettings((prev) => ({ ...prev, [key]: val }))

    const handleThemeChange = (theme: ThemePreference) => {
        setSettings((prev) => ({ ...prev, theme }))
        applyThemePreference(theme)
    }

    const handleSave = useCallback(async () => {
        if (!userId || saving) return
        setSaving(true)
        setSaveError('')
        setSaved(false)
        try {
            const ok = await saveUserSettings(userId, settings as unknown as Record<string, unknown>)
            if (ok) {
                setSaved(true)
                setTimeout(() => setSaved(false), 2500)
            } else {
                setSaveError('Could not save settings. Please try again.')
            }
        } finally {
            setSaving(false)
        }
    }, [userId, settings, saving])

    const handleDeleteAccount = useCallback(async () => {
        if (!userId) return
        await requestAccountErasure(userId)
        await signOut({ callbackUrl: '/' })
    }, [userId])

    const handleDataExport = useCallback(async () => {
        if (!userId) return
        setExporting(true)
        setPrivacyMessage('')
        const result = await exportUserData(userId)
        if (result.ok && result.data) {
            const blob = new Blob([JSON.stringify(result.data, null, 2)], {
                type: 'application/json',
            })
            const url = URL.createObjectURL(blob)
            const anchor = document.createElement('a')
            anchor.href = url
            anchor.download = `sentimind-data-export-${userId}.json`
            anchor.click()
            URL.revokeObjectURL(url)
            setPrivacyMessage('Data export generated.')
        } else {
            setPrivacyMessage(result.message || 'Could not generate data export.')
        }
        setExporting(false)
    }, [userId])

    const handleWithdrawConsent = useCallback(async () => {
        if (!userId) return
        setWithdrawingConsent(true)
        setPrivacyMessage('')
        const result = await withdrawUserConsent(
            userId,
            [
                'WELLNESS_CHAT',
                'MOOD_ANALYTICS',
                'PERSONALIZATION',
                'CRISIS_SAFETY',
                'CRISIS_LOCATION',
                'EMERGENCY_CONTACT_ALERTS',
                'VOICE_ANALYSIS',
            ],
            'withdrawn_from_profile'
        )
        if (result.ok) {
            setSettings((prev) => ({
                ...prev,
                voiceAnalysisConsent: false,
                shareLocationInCrisis: false,
                emergencyContactConsent: false,
            }))
        }
        setPrivacyMessage(result.message || (result.ok ? 'Consent withdrawn.' : 'Could not withdraw consent.'))
        setWithdrawingConsent(false)
    }, [userId])

    const initials = displayName
        ? displayName.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2)
        : '?'

    return (
        <div className="flex h-screen w-full bg-slate-50 overflow-hidden">
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                <Navbar name={displayName} />

                <div className="flex-1 overflow-y-auto">
                    <div className="max-w-4xl mx-auto p-6 w-full">

                        {/* Profile header */}
                        <div className="flex items-center gap-5 mb-8">
                            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-slate-950 to-cyan-700 flex items-center justify-center shadow-md shrink-0">
                                {profileLoading ? (
                                    <Loader className="w-6 h-6 text-white animate-spin" />
                                ) : (
                                    <span className="text-white text-2xl font-bold">{initials}</span>
                                )}
                            </div>
                            <div>
                                {profileLoading ? (
                                    <div className="space-y-2">
                                        <div className="h-5 w-36 bg-slate-200 rounded animate-pulse" />
                                        <div className="h-4 w-48 bg-slate-100 rounded animate-pulse" />
                                    </div>
                                ) : (
                                    <>
                                        <h1 className="text-xl font-black text-slate-900">{displayName || 'Your Profile'}</h1>
                                        <p className="text-sm text-slate-500">{displayEmail}</p>
                                    </>
                                )}
                            </div>
                        </div>

                        <div className="flex flex-col gap-4 sm:flex-row sm:gap-6">
                            {/* Sidebar tabs */}
                            <nav className="hidden sm:flex flex-col gap-1 w-44 shrink-0">
                                {TABS.map((tab) => (
                                    <SettingsTab
                                        key={tab.id}
                                        label={tab.label}
                                        icon={tab.icon}
                                        active={activeTab === tab.id}
                                        onClick={() => setActiveTab(tab.id)}
                                    />
                                ))}
                                <div className="mt-4 border-t border-slate-100 pt-4">
                                    <button
                                        onClick={() => signOut({ callbackUrl: '/' })}
                                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-red-500 hover:bg-red-50 transition-colors text-left"
                                    >
                                        <LogOut className="w-4 h-4 shrink-0" />
                                        Sign Out
                                    </button>
                                </div>
                            </nav>

                            <div className="sm:hidden">
                                <label htmlFor="profile-section" className="sr-only">Profile section</label>
                                <select
                                    id="profile-section"
                                    value={activeTab}
                                    onChange={(event) => setActiveTab(event.target.value as TabId)}
                                    className="mb-4 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm focus:border-slate-400 focus:outline-none"
                                >
                                    {TABS.map((tab) => (
                                        <option key={tab.id} value={tab.id}>
                                            {tab.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            {/* Settings panel */}
                            <div className="flex-1 min-w-0 space-y-4">
                                <div className="bg-white border border-slate-100 rounded-2xl p-6 shadow-sm">

                                    {activeTab === 'account' && (
                                        <div className="space-y-4 animate-fade-in">
                                            <h2 className="text-base font-bold text-slate-900">Account Information</h2>
                                            <div className="space-y-3">
                                                <div>
                                                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                                                        Full Name
                                                    </label>
                                                    <p className="text-sm font-semibold text-slate-800">{displayName || '—'}</p>
                                                </div>
                                                <div>
                                                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                                                        Email Address
                                                    </label>
                                                    <p className="text-sm font-semibold text-slate-800">{displayEmail || '—'}</p>
                                                </div>
                                                <div>
                                                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                                                        User ID
                                                    </label>
                                                    <p className="text-xs text-slate-400 font-mono">{userId}</p>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {activeTab === 'preferences' && (
                                        <div className="space-y-1 animate-fade-in">
                                            <h2 className="text-base font-bold text-slate-900 mb-4">Session &amp; Reminders</h2>
                                            <ToggleSetting
                                                label="Daily Check-in Reminder"
                                                description="Get a gentle nudge to reflect each day"
                                                checked={settings.dailyReminderEnabled}
                                                onChange={toggle('dailyReminderEnabled')}
                                            />
                                            <ToggleSetting
                                                label="Weekly Summary Email"
                                                description="Receive insight trends every Monday"
                                                checked={settings.weeklyEmailEnabled}
                                                onChange={toggle('weeklyEmailEnabled')}
                                            />
                                            <ToggleSetting
                                                label="Session Auto-save"
                                                description="Automatically save progress during chat"
                                                checked={settings.sessionAutoSave}
                                                onChange={toggle('sessionAutoSave')}
                                            />
                                        </div>
                                    )}

                                    {activeTab === 'privacy' && (
                                        <div className="space-y-4 animate-fade-in">
                                            <h2 className="text-base font-bold text-slate-900">Privacy &amp; Data</h2>
                                            <div className="bg-slate-50 rounded-xl p-4 text-sm text-slate-600 leading-relaxed">
                                                Your data is encrypted in transit and at rest. SentiMind records consent,
                                                audit events, and data-rights requests, and your wellness data is never sold.
                                            </div>
                                            <ToggleSetting
                                                label="Anonymous Mode"
                                                description="Your identity will be hidden in chat sessions"
                                                checked={settings.anonymousMode}
                                                onChange={toggle('anonymousMode')}
                                            />
                                            <ToggleSetting
                                                label="Voice Tone Analysis"
                                                description="Allow acoustic voice features to be analyzed when you send voice messages"
                                                checked={settings.voiceAnalysisConsent}
                                                onChange={toggle('voiceAnalysisConsent')}
                                            />
                                            <div className="rounded-xl border border-slate-200 bg-white p-4">
                                                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                                    <div>
                                                        <p className="text-sm font-bold text-slate-900">Data rights</p>
                                                        <p className="mt-1 text-xs leading-5 text-slate-500">
                                                            Export your account data or withdraw optional processing consent.
                                                        </p>
                                                    </div>
                                                    <div className="flex flex-wrap gap-2">
                                                        <Button
                                                            type="button"
                                                            variant="outline"
                                                            size="sm"
                                                            onClick={handleDataExport}
                                                            disabled={exporting || withdrawingConsent}
                                                            className="gap-2"
                                                        >
                                                            <Download className="h-4 w-4" />
                                                            {exporting ? 'Exporting...' : 'Export Data'}
                                                        </Button>
                                                        <Button
                                                            type="button"
                                                            variant="secondary"
                                                            size="sm"
                                                            onClick={handleWithdrawConsent}
                                                            disabled={exporting || withdrawingConsent}
                                                            className="gap-2"
                                                        >
                                                            <Ban className="h-4 w-4" />
                                                            {withdrawingConsent ? 'Withdrawing...' : 'Withdraw Consent'}
                                                        </Button>
                                                    </div>
                                                </div>
                                                {privacyMessage && (
                                                    <p className="mt-3 text-xs font-semibold text-slate-600">
                                                        {privacyMessage}
                                                    </p>
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {activeTab === 'crisis' && (
                                        <div className="space-y-4 animate-fade-in">
                                            <h2 className="text-base font-bold text-slate-900">Crisis Settings</h2>
                                            <ToggleSetting
                                                label="Share Location in Crisis"
                                                description="Allow emergency services to locate you if needed"
                                                checked={settings.shareLocationInCrisis}
                                                onChange={toggle('shareLocationInCrisis')}
                                            />
                                            <ToggleSetting
                                                label="Emergency Contact Alerts"
                                                description="Allow SentiMind to contact your saved trusted contacts during severe crisis events"
                                                checked={settings.emergencyContactConsent}
                                                onChange={toggle('emergencyContactConsent')}
                                            />
                                        </div>
                                    )}

                                    {activeTab === 'appearance' && (
                                        <div className="space-y-4 animate-fade-in">
                                            <h2 className="text-base font-bold text-slate-900">Appearance</h2>
                                            <div className="grid grid-cols-3 gap-3">
                                                {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
                                                    <button
                                                        key={value}
                                                        onClick={() => handleThemeChange(value)}
                                                        className={`flex min-h-24 flex-col items-center justify-center gap-2 rounded-xl border-2 p-4 text-sm font-semibold transition-all ${
                                                            settings.theme === value
                                                                ? 'border-slate-900 bg-slate-900 text-white'
                                                                : 'border-slate-200 text-slate-500 hover:border-slate-300'
                                                        }`}
                                                    >
                                                        <Icon className="h-5 w-5" />
                                                        {label}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {activeTab === 'about' && (
                                        <div className="space-y-4 animate-fade-in">
                                            <h2 className="text-base font-bold text-slate-900">About SentiMind</h2>
                                            <div className="space-y-2 text-sm text-slate-600">
                                                <p>
                                                    <strong>Disclaimer:</strong> SentiMind is designed to support mental
                                                    wellness and provide emotional insights. It is not a clinical medical
                                                    device and is not intended for diagnosing or treating medical conditions.
                                                    If you are in immediate distress, please contact emergency services or a
                                                    crisis hotline.
                                                </p>
                                                <div className="flex flex-wrap gap-3 pt-2">
                                                    <a href="/privacy" className="text-xs font-medium text-slate-700 hover:underline">Privacy Policy</a>
                                                    <a href="/terms" className="text-xs font-medium text-slate-700 hover:underline">Terms of Service</a>
                                                    <a href="#" className="text-xs font-medium text-slate-700 hover:underline">Support Center</a>
                                                </div>
                                                <p className="pt-2 text-xs text-slate-400">v1.0.0 (c) 2026 SentiMind AI</p>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {activeTab !== 'about' && (
                                    <div className="flex flex-wrap items-center gap-3">
                                        <Button variant="primary" onClick={handleSave} disabled={saving} className="px-8">
                                            {saving ? (
                                                <>
                                                    <Loader className="mr-2 h-4 w-4 animate-spin" />
                                                    Saving
                                                </>
                                            ) : (
                                                'Save Changes'
                                            )}
                                        </Button>
                                        {saved && (
                                            <div className="flex items-center gap-1.5 text-sm text-emerald-600 animate-fade-in">
                                                <CheckCircle className="w-4 h-4" />
                                                Saved!
                                            </div>
                                        )}
                                        {saveError && (
                                            <p className="text-sm font-semibold text-rose-600">{saveError}</p>
                                        )}
                                    </div>
                                )}

                                {activeTab === 'privacy' && (
                                    <DangerZone onDeleteAccount={handleDeleteAccount} />
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}

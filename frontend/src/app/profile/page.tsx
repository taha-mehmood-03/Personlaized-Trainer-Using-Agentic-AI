'use client'

import React, { useState, useCallback, useEffect } from 'react'
import { Navbar } from '@/components/layout/Navbar'
import { SettingsTab } from '@/components/profile/SettingsTab'
import { ToggleSetting } from '@/components/profile/ToggleSetting'
import { DangerZone } from '@/components/profile/DangerZone'
import { useSession, signOut } from 'next-auth/react'
import { saveUserSettings, deleteUserAccount, getUserProfile } from '@/actions/dashboard'
import { UserSettings } from '@/types'
import {
    User,
    Sliders,
    Shield,
    Phone,
    Palette,
    Info,
    LogOut,
    CheckCircle,
    Loader,
} from 'lucide-react'
import { Button } from '@/components/ui/button'

type TabId = 'account' | 'preferences' | 'privacy' | 'crisis' | 'appearance' | 'about'

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'account', label: 'Account', icon: <User className="w-4 h-4" /> },
    { id: 'preferences', label: 'Preferences', icon: <Sliders className="w-4 h-4" /> },
    { id: 'privacy', label: 'Privacy', icon: <Shield className="w-4 h-4" /> },
    { id: 'crisis', label: 'Crisis', icon: <Phone className="w-4 h-4" /> },
    { id: 'appearance', label: 'Appearance', icon: <Palette className="w-4 h-4" /> },
    { id: 'about', label: 'About', icon: <Info className="w-4 h-4" /> },
]

const DEFAULT_SETTINGS: UserSettings = {
    dailyReminderEnabled: true,
    weeklyEmailEnabled: true,
    sessionAutoSave: true,
    anonymousMode: false,
    shareLocationInCrisis: true,
    theme: 'light',
}

export default function ProfilePage() {
    const { data: session } = useSession()
    const userId = session?.user?.id ?? null
    const [activeTab, setActiveTab] = useState<TabId>('account')
    const [saved, setSaved] = useState(false)
    const [profileLoading, setProfileLoading] = useState(true)
    const [displayName, setDisplayName] = useState('')
    const [displayEmail, setDisplayEmail] = useState('')
    const [settings, setSettings] = useState<UserSettings>(DEFAULT_SETTINGS)

    // Load real profile from API
    useEffect(() => {
        if (!userId) { setProfileLoading(false); return }
        getUserProfile(userId).then((profile) => {
            if (profile) {
                setDisplayName(profile.name || session?.user?.name || '')
                setDisplayEmail(profile.email || session?.user?.email || '')
                setSettings({ ...DEFAULT_SETTINGS, ...profile.settings })
            } else {
                setDisplayName(session?.user?.name || '')
                setDisplayEmail(session?.user?.email || '')
            }
            setProfileLoading(false)
        })
    }, [userId, session])

    const toggle = (key: keyof UserSettings) => (val: boolean) =>
        setSettings((prev) => ({ ...prev, [key]: val }))

    const handleSave = useCallback(async () => {
        if (!userId) return
        const ok = await saveUserSettings(userId, settings as unknown as Record<string, unknown>)
        if (ok) {
            setSaved(true)
            setTimeout(() => setSaved(false), 2500)
        }
    }, [userId, settings])

    const handleDeleteAccount = useCallback(async () => {
        if (!userId) return
        await deleteUserAccount(userId)
        await signOut({ callbackUrl: '/' })
    }, [userId])

    const initials = displayName
        ? displayName.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2)
        : '?'

    return (
        <div className="flex h-screen w-full bg-slate-50 overflow-hidden">
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                <Navbar />

                <div className="flex-1 overflow-y-auto">
                    <div className="max-w-4xl mx-auto p-6 w-full">

                        {/* Profile header */}
                        <div className="flex items-center gap-5 mb-8">
                            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-purple-500 to-teal-400 flex items-center justify-center shadow-md shrink-0">
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

                        <div className="flex gap-6">
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
                                                Your data is end-to-end encrypted. SentiMind strictly adheres to privacy
                                                regulations and your personal health data is never sold to third parties.
                                            </div>
                                            <ToggleSetting
                                                label="Anonymous Mode"
                                                description="Your identity will be hidden in chat sessions"
                                                checked={settings.anonymousMode}
                                                onChange={toggle('anonymousMode')}
                                            />
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
                                        </div>
                                    )}

                                    {activeTab === 'appearance' && (
                                        <div className="space-y-4 animate-fade-in">
                                            <h2 className="text-base font-bold text-slate-900">Appearance</h2>
                                            <div className="grid grid-cols-3 gap-3">
                                                {(['light', 'dark', 'system'] as const).map((t) => (
                                                    <button
                                                        key={t}
                                                        onClick={() => setSettings((s) => ({ ...s, theme: t }))}
                                                        className={`p-4 rounded-xl border-2 text-sm font-semibold capitalize transition-all ${
                                                            settings.theme === t
                                                                ? 'border-purple-500 bg-purple-50 text-purple-700'
                                                                : 'border-slate-200 text-slate-500 hover:border-slate-300'
                                                        }`}
                                                    >
                                                        {t === 'light' ? '☀️' : t === 'dark' ? '🌙' : '⚙️'}
                                                        <br />
                                                        {t}
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
                                                    <a href="#" className="text-purple-600 hover:underline font-medium text-xs">Privacy Policy</a>
                                                    <a href="#" className="text-purple-600 hover:underline font-medium text-xs">Terms of Service</a>
                                                    <a href="#" className="text-purple-600 hover:underline font-medium text-xs">Support Center</a>
                                                </div>
                                                <p className="text-xs text-slate-400 pt-2">v1.0.0 © 2024 SentiMind AI</p>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {activeTab !== 'about' && (
                                    <div className="flex items-center gap-3">
                                        <Button variant="primary" onClick={handleSave} className="px-8">
                                            Save Changes
                                        </Button>
                                        {saved && (
                                            <div className="flex items-center gap-1.5 text-sm text-emerald-600 animate-fade-in">
                                                <CheckCircle className="w-4 h-4" />
                                                Saved!
                                            </div>
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

'use client'

import React from 'react'
import { Navbar } from '@/components/layout/Navbar'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/components/providers/AuthProvider'

export default function ProfilePage() {
  const { logout } = useAuth()

  return (
    <div className="flex h-screen w-full bg-slate-50 overflow-hidden">
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Navbar />
        <div className="flex-1 overflow-y-auto p-6 max-w-3xl mx-auto w-full space-y-8">
          
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Your Profile</h1>
            <p className="text-slate-500">Manage your account settings and preferences.</p>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-6">
            <div className="flex items-center gap-4 border-b border-slate-100 pb-6">
              <div className="w-16 h-16 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-xl font-bold text-slate-400">
                U
              </div>
              <div>
                <h3 className="text-lg font-semibold text-slate-900">Jane Doe</h3>
                <p className="text-sm text-slate-500">jane@example.com</p>
              </div>
            </div>

            <div className="space-y-4">
              <h4 className="font-medium text-slate-900">Preferences</h4>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-slate-600">Daily Reminder</span>
                <input type="checkbox" className="toggle" defaultChecked />
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-slate-600">Dark Mode</span>
                <input type="checkbox" className="toggle" />
              </div>
            </div>

            <div className="pt-6 border-t border-slate-100">
              <Button onClick={logout} variant="destructive" className="w-full sm:w-auto">
                Sign Out
              </Button>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  )
}

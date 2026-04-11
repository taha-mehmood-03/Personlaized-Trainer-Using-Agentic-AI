import React from 'react'
import Link from 'next/link'
import { Sparkles } from 'lucide-react'

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md mb-8 flex flex-col items-center">
        <Link href="/">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-purple-500 to-teal-400 p-0.5 shadow-sm mb-4">
            <div className="w-full h-full bg-white rounded-2xl flex items-center justify-center">
              <Sparkles className="w-6 h-6 text-purple-600" />
            </div>
          </div>
        </Link>
        <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900">
          SentiMind
        </h2>
        <p className="mt-2 text-center text-sm text-slate-600">
          Your AI wellness companion
        </p>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow-sm border border-slate-200 sm:rounded-2xl sm:px-10">
          {children}
        </div>
      </div>
    </div>
  )
}

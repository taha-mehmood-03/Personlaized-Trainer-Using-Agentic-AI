import React from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Phone, ShieldAlert } from 'lucide-react'

export default function CrisisPage() {
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
        </div>

        <div className="space-y-4">
          <Button asChild size="lg" className="w-full bg-rose-600 hover:bg-rose-700 text-white h-16 text-lg rounded-2xl shadow-rose-200 shadow-xl border-none">
            <a href="tel:988">
              <Phone className="w-5 h-5 mr-3" />
              Call 988 (National Suicide Prevention Lifeline)
            </a>
          </Button>
          
          <Button asChild variant="outline" size="lg" className="w-full h-14 text-base rounded-xl border-slate-300">
            <a href="sms:741741">
              Text HOME to 741741 (Crisis Text Line)
            </a>
          </Button>
        </div>

        <div className="pt-8 border-t border-slate-100">
          <Button asChild variant="ghost" className="text-slate-500">
            <Link href="/chat">Return to Chat</Link>
          </Button>
        </div>
      </div>
    </div>
  )
}

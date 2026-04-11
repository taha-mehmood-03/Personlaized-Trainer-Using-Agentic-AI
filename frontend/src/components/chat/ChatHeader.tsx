import { Sparkles, Circle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

interface ChatHeaderProps {
  emotion: string | null
  sentiment: string | null
}

export function ChatHeader({ emotion, sentiment }: ChatHeaderProps) {
  return (
    <div className="flex flex-wrap items-center justify-between py-3">
      {/* Target details */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-teal-400 p-0.5 shadow-sm">
          <div className="w-full h-full bg-white rounded-full flex items-center justify-center border-2 border-white">
            <Sparkles className="w-5 h-5 text-purple-600" />
          </div>
        </div>
        <div>
          <h2 className="text-sm font-bold text-slate-800 flex items-center gap-2 tracking-tight">
            SentiMind AI
            <span className="flex items-center text-[10px] bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded-full border border-emerald-100 uppercase tracking-widest font-bold">
              <Circle className="w-1.5 h-1.5 fill-current mr-1 animate-pulse" />
              Listening
            </span>
          </h2>
          <p className="text-xs text-slate-500 font-medium">Your Supportive Companion</p>
        </div>
      </div>

      {/* Dynamic Emotion Badge (if any) */}
      <div className="flex gap-2">
        {emotion && (
          <Badge variant="emotion" className="capitalize shadow-sm">
            Detecting: {emotion}
          </Badge>
        )}
        <Badge variant="secondary" className="bg-blue-50 text-blue-700 border-blue-200">
          Friend Mode
        </Badge>
      </div>
    </div>
  )
}

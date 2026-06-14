'use client'

import { useState, useEffect } from 'react'
import { Mic, MicOff } from 'lucide-react'
import { VoiceResult } from '@/types'

interface VoiceIndicatorProps {
  isRecording: boolean
  voiceResult: VoiceResult | null
  onStartRecording: () => void
  onStopRecording: () => void
}

const EMOTION_GRADIENT: Record<string, string> = {
  joy: 'from-yellow-400 to-orange-400',
  sadness: 'from-blue-400 to-indigo-500',
  anger: 'from-red-400 to-red-600',
  fear: 'from-cyan-500 to-slate-700',
  disgust: 'from-green-400 to-emerald-600',
  surprise: 'from-pink-400 to-rose-500',
  neutral: 'from-slate-400 to-slate-500',
}

const EMOTION_EMOJI: Record<string, string> = {
  joy: '😊', sadness: '😔', anger: '😠',
  fear: '😨', disgust: '🤢', surprise: '😲', neutral: '😐',
}

export function VoiceIndicator({ isRecording, voiceResult, onStartRecording, onStopRecording }: VoiceIndicatorProps) {
  const [barHeights, setBarHeights] = useState<number[]>(Array(20).fill(20))

  useEffect(() => {
    if (!isRecording) { setBarHeights(Array(20).fill(20)); return }
    const id = setInterval(() => {
      setBarHeights(prev => prev.map((_, i) => Math.abs(Math.sin((i + Date.now() / 200)) * 70) + 10))
    }, 80)
    return () => clearInterval(id)
  }, [isRecording])

  const emotion = voiceResult?.emotion?.toLowerCase() ?? 'neutral'

  return (
    <div className="space-y-3 mb-3 animate-fade-in">
      {/* Recording toggle row */}
      <div className="flex items-center gap-3">
        <button
          onClick={isRecording ? onStopRecording : onStartRecording}
          className={`p-3 rounded-full transition-all ${
            isRecording
              ? 'bg-red-500 text-white shadow-lg shadow-red-500/40 animate-pulse ring-4 ring-red-500/20'
              : 'bg-gradient-to-br from-cyan-400 to-blue-500 text-white shadow-md hover:shadow-lg'
          }`}
        >
          {isRecording ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
        </button>
        <div>
          <p className="text-sm font-semibold text-slate-700">
            {isRecording ? '🔴 Recording…' : '🎤 Ready to listen'}
          </p>
          <p className="text-xs text-slate-400">
            {isRecording ? 'Speak naturally, then click stop' : 'Click mic for voice message'}
          </p>
        </div>
      </div>

      {/* Waveform */}
      {isRecording && (
        <div className="bg-gradient-to-r from-cyan-50 to-blue-50 border border-cyan-200 rounded-xl px-4 py-3 shadow-inner">
          <div className="flex items-center justify-between gap-1 h-10">
            {barHeights.map((h, i) => (
              <div
                key={i}
                className="flex-1 bg-gradient-to-t from-cyan-400 to-blue-500 rounded-full transition-all duration-75 opacity-80"
                style={{ height: `${h}%` }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Detected voice emotion */}
      {voiceResult && !isRecording && (
        <div className={`bg-gradient-to-br ${EMOTION_GRADIENT[emotion] ?? EMOTION_GRADIENT.neutral} p-4 rounded-xl text-white shadow-md`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-2xl">{EMOTION_EMOJI[emotion] ?? '🎙️'}</span>
              <div>
                <p className="font-semibold capitalize">{voiceResult.emotion} detected</p>
                <p className="text-sm opacity-80">Confidence: {Math.round(voiceResult.confidence * 100)}%</p>
              </div>
            </div>
            <p className="text-2xl font-bold">{Math.round(voiceResult.confidence * 100)}%</p>
          </div>
          {voiceResult.acoustic_features && (
            <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-white/25 text-xs">
              <div><p className="opacity-70">Pitch</p><p className="font-bold">{voiceResult.acoustic_features.pitch_mean?.toFixed(0) ?? '—'} Hz</p></div>
              <div><p className="opacity-70">Loudness</p><p className="font-bold">{voiceResult.acoustic_features.loudness_mean?.toFixed(2) ?? '—'}</p></div>
              <div><p className="opacity-70">Speed</p><p className="font-bold">{voiceResult.acoustic_features.speech_rate?.toFixed(1) ?? '—'} syl/s</p></div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

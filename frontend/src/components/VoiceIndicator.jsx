import React, { useState, useEffect } from 'react'
import { Mic, MicOff, Volume2 } from 'lucide-react'

export default function VoiceIndicator({ 
  isRecording, 
  voiceEmotion, 
  voiceConfidence, 
  acousticFeatures,
  onStartRecording,
  onStopRecording 
}) {
  const [audioLevel, setAudioLevel] = useState(0)
  const [animationKey, setAnimationKey] = useState(0)

  useEffect(() => {
    if (isRecording) {
      const interval = setInterval(() => {
        setAudioLevel(Math.random() * 100)
        setAnimationKey(k => k + 1)
      }, 100)
      return () => clearInterval(interval)
    } else {
      setAudioLevel(0)
    }
  }, [isRecording])

  const emotionColors = {
    joy: 'from-yellow-400 to-orange-400',
    sadness: 'from-blue-400 to-indigo-500',
    anger: 'from-red-400 to-red-600',
    fear: 'from-purple-400 to-purple-600',
    disgust: 'from-green-400 to-teal-500',
    surprise: 'from-pink-400 to-rose-500',
    neutral: 'from-gray-400 to-gray-500',
  }

  const emotionEmoji = {
    joy: '😊',
    sadness: '😔',
    anger: '😠',
    fear: '😨',
    disgust: '🤢',
    surprise: '😲',
    neutral: '😐',
  }

  return (
    <div className="space-y-4">
      {/* Recording Button & Status */}
      <div className="flex items-center gap-3">
        <button
          onClick={isRecording ? onStopRecording : onStartRecording}
          className={`p-4 rounded-full transition-all duration-300 transform hover:scale-110 ${
            isRecording
              ? 'bg-red-500 text-white shadow-lg shadow-red-500/50 animate-recording-pulse'
              : 'bg-gradient-to-br from-cyan-400 to-blue-500 text-white shadow-md hover:shadow-lg'
          }`}
        >
          {isRecording ? (
            <MicOff className="w-6 h-6" />
          ) : (
            <Mic className="w-6 h-6" />
          )}
        </button>

        <div className="flex-1">
          <div className="text-sm font-semibold text-gray-700">
            {isRecording ? '🔴 Recording...' : '🎤 Ready to listen'}
          </div>
          <p className="text-xs text-gray-500">
            {isRecording ? 'Click stop or speak naturally' : 'Click mic to start voice message'}
          </p>
        </div>
      </div>

      {/* Audio Waveform Visualization */}
      {isRecording && (
        <div className="bg-gradient-to-r from-cyan-50 to-blue-50 p-4 rounded-xl border-2 border-cyan-200">
          <div className="flex items-center justify-between gap-1 h-12">
            {Array.from({ length: 20 }).map((_, i) => (
              <div
                key={`${animationKey}-${i}`}
                className="flex-1 bg-gradient-to-t from-cyan-400 to-blue-500 rounded-full transition-all duration-100"
                style={{
                  height: `${Math.sin((i + animationKey) / 5) * 50 + 50}%`,
                  opacity: 0.6 + Math.random() * 0.4,
                }}
              />
            ))}
          </div>
          <div className="mt-2 text-center text-xs font-medium text-cyan-700">
            Audio Level: {Math.round(audioLevel)}%
          </div>
        </div>
      )}

      {/* Voice Emotion Detection (if available) */}
      {voiceEmotion && !isRecording && (
        <div className={`bg-gradient-to-br ${emotionColors[voiceEmotion] || emotionColors.neutral} p-4 rounded-xl text-white shadow-md`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-3xl">{emotionEmoji[voiceEmotion]}</span>
              <div>
                <div className="font-semibold capitalize">{voiceEmotion} detected</div>
                <div className="text-sm opacity-90">Confidence: {(voiceConfidence * 100).toFixed(0)}%</div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold">{(voiceConfidence * 100).toFixed(0)}%</div>
            </div>
          </div>

          {/* Acoustic Features */}
          {acousticFeatures && (
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs pt-3 border-t border-white/30">
              <div>
                <div className="opacity-75">Pitch</div>
                <div className="font-bold">{acousticFeatures.pitch_mean?.toFixed(0) || '—'} Hz</div>
              </div>
              <div>
                <div className="opacity-75">Loudness</div>
                <div className="font-bold">{acousticFeatures.loudness_mean?.toFixed(2) || '—'}</div>
              </div>
              <div>
                <div className="opacity-75">Speed</div>
                <div className="font-bold">{acousticFeatures.speech_rate?.toFixed(1) || '—'} syl/s</div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

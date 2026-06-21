'use client'

import { KeyboardEvent, useRef, useState } from 'react'
import { Loader, Mic, MicOff, Send, ShieldCheck } from 'lucide-react'
import { devError, devLog } from '@/lib/logger'

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

interface SpeechRecognitionLike {
  continuous: boolean
  interimResults: boolean
  lang: string
  onstart: (() => void) | null
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<{
    isFinal: boolean
    0: { transcript: string }
  }>
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
}

const PROMPTS = [
  'I want to talk through what happened today.',
  'Can you help me understand this feeling?',
  'I need support, but not an exercise yet.',
]

export function ChatInput({
  isLoading,
  postCrisisSafetyCheck = false,
  onSend,
}: {
  isLoading: boolean
  postCrisisSafetyCheck?: boolean
  onSend: (text: string, audioData?: string) => void
}) {
  const [input, setInput] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [isProcessingAudio, setIsProcessingAudio] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const audioMimeTypeRef = useRef('audio/webm')
  const transcriptRef = useRef('')
  const recordingFinalizedRef = useRef(false)
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const resetTextarea = () => {
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const submitText = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || isLoading || isProcessingAudio) return
    onSend(trimmed)
    setInput('')
    resetTextarea()
  }

  const handleSend = () => submitText(input)

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 170)}px`
  }

  const blobToDataUrl = (blob: Blob) =>
    new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(reader.result as string)
      reader.onerror = reject
      reader.readAsDataURL(blob)
    })

  const sendWithAudio = async (chunks: Blob[], text: string) => {
    const trimmed = text.trim()
    setIsProcessingAudio(true)
    try {
      if (chunks.length > 0) {
        const rawBlob = new Blob(chunks, { type: audioMimeTypeRef.current })
        const rawAudioData = await blobToDataUrl(rawBlob)
        try {
          const { blobToWavBase64 } = await import('@/lib/audioWav')
          const wavBase64 = await blobToWavBase64(rawBlob)
          devLog('[VOICE] Sending WAV audio payload', { transcriptChars: trimmed.length, audioChars: wavBase64.length })
          onSend(trimmed, wavBase64)
        } catch (err) {
          devError('[VOICE] WAV conversion failed, sending raw audio:', err)
          devLog('[VOICE] Sending raw audio payload', { transcriptChars: trimmed.length, audioChars: rawAudioData.length })
          onSend(trimmed, rawAudioData)
        }
      } else if (trimmed) {
        onSend(trimmed)
      }
    } catch (err) {
      devError('[VOICE] Audio send failed, sending transcript only:', err)
      if (trimmed) onSend(trimmed)
    } finally {
      setIsProcessingAudio(false)
      setInput('')
      resetTextarea()
    }
  }

  const finalizeRecording = (textOverride?: string) => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    if (recordingFinalizedRef.current) return
    recordingFinalizedRef.current = true

    const transcript = (textOverride ?? transcriptRef.current ?? input).trim()
    const recorder = mediaRecorderRef.current
    const send = () => {
      void sendWithAudio([...audioChunksRef.current], transcript).finally(() => {
        recognitionRef.current = null
        mediaRecorderRef.current = null
      })
    }

    try {
      recognitionRef.current?.stop()
    } catch (err) {
      devError('[VOICE] Recognition stop failed:', err)
    }

    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = send
      try {
        recorder.requestData()
      } catch {
        // requestData is best-effort; stop still flushes data in supported browsers.
      }
      recorder.stop()
      recorder.stream.getTracks().forEach((track) => track.stop())
    } else {
      send()
    }

    setIsRecording(false)
  }

  const stopRecording = () => {
    finalizeRecording()
  }

  const toggleRecording = async () => {
    if (isRecording) {
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current)
        silenceTimerRef.current = null
      }
      stopRecording()
      return
    }

    try {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
      if (!SpeechRecognition) {
        alert('Voice input is not supported in this browser. Try Chrome or Edge.')
        return
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : ''

      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)

      mediaRecorderRef.current = mediaRecorder
      audioMimeTypeRef.current = mediaRecorder.mimeType || mimeType || 'audio/webm'
      audioChunksRef.current = []
      transcriptRef.current = ''
      recordingFinalizedRef.current = false
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data)
      }
      mediaRecorder.start(250)

      const recognition = new SpeechRecognition()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'
      recognition.onstart = () => setIsRecording(true)
      recognition.onerror = (event) => {
        devError('[VOICE] Recognition error:', event.error)
        finalizeRecording()
      }
      recognition.onend = () => {
        setIsRecording(false)
        if (!recordingFinalizedRef.current && mediaRecorderRef.current?.state !== 'inactive') {
          finalizeRecording()
        }
      }
      recognition.onresult = (event) => {
        let finalTranscript = ''
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript
        }

        if (!finalTranscript.trim()) return
        const trimmed = finalTranscript.trim()
        transcriptRef.current = [transcriptRef.current, trimmed].filter(Boolean).join(' ').trim()
        setInput(transcriptRef.current)

        // Debounce: wait 2 s of silence before sending.
        // Resets on every new final result so multi-sentence speech accumulates naturally.
        if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current)
        silenceTimerRef.current = setTimeout(() => {
          finalizeRecording(transcriptRef.current)
        }, 2000)
      }

      recognition.start()
      recognitionRef.current = recognition
    } catch (err) {
      devError('[VOICE] Recording start failed:', err)
      mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop())
      setIsRecording(false)
    }
  }

  return (
    <footer className="shrink-0 border-t border-slate-200 bg-white px-4 py-4">
      <div className="mx-auto max-w-4xl space-y-3">
        {postCrisisSafetyCheck ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-800">
            Safety check active: reply whether you are safe now or still in immediate danger.
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => setInput(prompt)}
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-white"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}

        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-2 shadow-sm focus-within:border-slate-300 focus-within:bg-white">
          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              onInput={handleInput}
              placeholder={
                isProcessingAudio
                  ? 'Analyzing voice...'
                  : isRecording
                    ? 'Listening... click mic to stop'
                    : postCrisisSafetyCheck
                      ? 'Are you safe now, or still in danger?'
                      : 'Share what is happening, or ask for support...'
              }
              rows={1}
              className="min-h-12 max-h-[170px] flex-1 resize-none bg-transparent px-3 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none"
              disabled={isRecording || isProcessingAudio}
            />

            <button
              type="button"
              onClick={toggleRecording}
              disabled={isLoading || isProcessingAudio}
              title={isRecording ? 'Stop recording' : 'Voice message'}
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition-all ${
                isRecording
                  ? 'bg-rose-600 text-white shadow-sm'
                  : isProcessingAudio
                    ? 'bg-amber-500 text-white'
                    : 'bg-teal-50 text-teal-600 border border-teal-200 shadow-sm hover:bg-teal-100 hover:border-teal-300 disabled:opacity-50'
              }`}
            >
              {isProcessingAudio ? (
                <Loader className="h-5 w-5 animate-spin" />
              ) : isRecording ? (
                <MicOff className="h-5 w-5" />
              ) : (
                <Mic className="h-5 w-5" />
              )}
            </button>

            <button
              type="button"
              onClick={handleSend}
              disabled={!input.trim() || isLoading || isProcessingAudio}
              title="Send"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-600 text-white shadow-sm transition-all hover:from-teal-600 hover:to-cyan-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isLoading ? <Loader className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
            </button>
          </div>
        </div>

        <p className="flex items-center justify-center gap-1.5 text-center text-[11px] text-slate-400">
          <ShieldCheck className="h-3.5 w-3.5" />
          Supportive companion only. For emergencies, contact local crisis services immediately.
        </p>
      </div>
    </footer>
  )
}

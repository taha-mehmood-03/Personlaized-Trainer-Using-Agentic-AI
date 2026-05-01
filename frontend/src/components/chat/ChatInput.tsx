'use client'

import { useState, useRef, KeyboardEvent } from 'react'
import { Send, Mic, MicOff, Loader } from 'lucide-react'

// ─── WAV Encoder (Web Audio API → 16kHz mono WAV) ──────────────────────────
// Runs entirely in the browser — no ffmpeg/system dependencies.
// Output is a standard RIFF/WAV file that scipy, librosa, and Whisper can all read.

function writeString(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}

function floatTo16BitPCM(output: DataView, offset: number, input: Float32Array) {
  for (let i = 0; i < input.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, input[i]))
    output.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
}

function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const numSamples = samples.length
  const buf = new ArrayBuffer(44 + numSamples * 2)
  const view = new DataView(buf)
  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + numSamples * 2, true)
  writeString(view, 8, 'WAVE')
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)             // chunk size
  view.setUint16(20, 1, true)              // PCM format
  view.setUint16(22, 1, true)              // mono
  view.setUint32(24, sampleRate, true)     // sample rate
  view.setUint32(28, sampleRate * 2, true) // byte rate
  view.setUint16(32, 2, true)              // block align
  view.setUint16(34, 16, true)             // bits per sample
  writeString(view, 36, 'data')
  view.setUint32(40, numSamples * 2, true)
  floatTo16BitPCM(view, 44, samples)
  return buf
}

async function blobToWavBase64(blob: Blob, targetSampleRate = 16000): Promise<string> {
  const arrayBuffer = await blob.arrayBuffer()
  // Decode WebM/Opus/OGG → PCM float using the browser's built-in codec
  const audioCtx = new AudioContext({ sampleRate: targetSampleRate })
  const decoded = await audioCtx.decodeAudioData(arrayBuffer)
  audioCtx.close()
  // Mix down to mono (take channel 0)
  const mono = decoded.getChannelData(0)
  // Encode as 16-bit PCM WAV
  const wavBuffer = encodeWav(mono, targetSampleRate)
  const wavBlob = new Blob([wavBuffer], { type: 'audio/wav' })
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.readAsDataURL(wavBlob)
    reader.onloadend = () => resolve(reader.result as string)
    reader.onerror = reject
  })
}
// ───────────────────────────────────────────────────────────────────────────

export function ChatInput({
  isLoading,
  onSend,
}: {
  isLoading: boolean
  onSend: (text: string, audioData?: string) => void
}) {
  const [input, setInput] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [isProcessingAudio, setIsProcessingAudio] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const recognitionRef = useRef<any>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])

  const handleSend = () => {
    const text = input.trim()
    if (!text || isLoading) return
    onSend(text)
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  // Convert captured chunks to WAV and call onSend
  const sendWithAudio = async (chunks: Blob[], text: string) => {
    setIsProcessingAudio(true)
    try {
      if (chunks.length > 0) {
        const rawBlob = new Blob(chunks, { type: 'audio/webm' })
        console.log('[VOICE] Raw blob size:', rawBlob.size, 'bytes — converting to WAV...')
        const wavBase64 = await blobToWavBase64(rawBlob)
        console.log('[VOICE] Converted to 16kHz mono WAV — sending with text:', text)
        onSend(text, wavBase64)
      } else {
        console.warn('[VOICE] No audio chunks — sending text only')
        onSend(text)
      }
    } catch (err) {
      console.error('[VOICE] WAV conversion failed — sending text only:', err)
      onSend(text)
    } finally {
      setIsProcessingAudio(false)
      setInput('')
    }
  }

  const toggleRecording = () => {
    if (isRecording) {
      recognitionRef.current?.stop()
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
        mediaRecorderRef.current.stream.getTracks().forEach((t: any) => t.stop())
      }
      return
    }

    try {
      const SpeechRecognition =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (!SpeechRecognition) {
        alert('Voice input is not supported in this browser. Try Chrome or Edge.')
        return
      }

      const recognition = new SpeechRecognition()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'

      recognition.onstart = () => setIsRecording(true)

      recognition.onresult = (event: any) => {
        let finalTranscript = ''
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript
        }

        if (finalTranscript) {
          const trimmed = finalTranscript.trim()
          setInput(trimmed)
          recognition.stop()

          if (
            mediaRecorderRef.current &&
            mediaRecorderRef.current.state !== 'inactive'
          ) {
            // Recorder still running → stop and send in onstop callback
            mediaRecorderRef.current.onstop = () => {
              sendWithAudio([...audioChunksRef.current], trimmed)
            }
            mediaRecorderRef.current.stop()
            mediaRecorderRef.current.stream.getTracks().forEach((t: any) => t.stop())
          } else {
            // Recorder already stopped (user clicked stop button) → send immediately
            sendWithAudio([...audioChunksRef.current], trimmed)
          }
        }
      }

      // Start MediaRecorder in parallel with SpeechRecognition
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then((stream) => {
          const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus'
            : MediaRecorder.isTypeSupported('audio/webm')
            ? 'audio/webm'
            : ''

          const mediaRecorder = mimeType
            ? new MediaRecorder(stream, { mimeType })
            : new MediaRecorder(stream)

          mediaRecorderRef.current = mediaRecorder
          audioChunksRef.current = []

          mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunksRef.current.push(e.data)
          }

          // Collect a chunk every 250ms for reliability
          mediaRecorder.start(250)
          console.log('[VOICE] MediaRecorder started | mimeType:', mediaRecorder.mimeType)
        })
        .catch((err) => console.error('[VOICE] Mic access error:', err))

      recognition.onerror = (event: any) => {
        console.error('[VOICE] Recognition error:', event.error)
        setIsRecording(false)
      }

      recognition.onend = () => setIsRecording(false)

      recognition.start()
      recognitionRef.current = recognition
    } catch (err) {
      console.error(err)
      setIsRecording(false)
    }
  }

  return (
    <div className="bg-white border-t border-gray-100 px-5 py-4 shrink-0">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-end gap-3">
          {/* Textarea */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onInput={handleInput}
              placeholder={
                isProcessingAudio
                  ? 'Analysing voice...'
                  : isRecording
                  ? 'Listening... click mic to stop'
                  : 'Type your thoughts here...'
              }
              rows={1}
              className="w-full resize-none px-4 py-3 pr-4 text-sm text-gray-800 placeholder-gray-400 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-300 focus:border-purple-300 transition-all"
              style={{ minHeight: '48px', maxHeight: '160px' }}
              disabled={isRecording || isProcessingAudio}
            />
          </div>

          {/* Mic button */}
          <button
            onClick={toggleRecording}
            disabled={isLoading || isProcessingAudio}
            title={isRecording ? 'Stop recording' : 'Voice message'}
            className={`p-3 rounded-xl transition-all shrink-0 ${
              isRecording
                ? 'bg-red-500 text-white shadow-lg shadow-red-500/40 animate-pulse'
                : isProcessingAudio
                ? 'bg-yellow-400 text-white cursor-wait'
                : 'bg-teal-500 text-white hover:bg-teal-600 hover:shadow-[0_4px_12px_rgba(20,184,166,0.3)] disabled:opacity-50'
            }`}
          >
            {isProcessingAudio ? (
              <Loader className="w-5 h-5 animate-spin" />
            ) : isRecording ? (
              <MicOff className="w-5 h-5" />
            ) : (
              <Mic className="w-5 h-5" />
            )}
          </button>

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading || isProcessingAudio}
            title="Send (Enter)"
            className="p-3 rounded-xl bg-gradient-to-br from-purple-600 to-purple-500 text-white hover:shadow-lg hover:shadow-purple-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:scale-105 active:scale-95 shrink-0"
          >
            {isLoading ? <Loader className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
          </button>
        </div>

        {/* Status / Disclaimer */}
        <p className="text-center text-[11px] text-gray-400 mt-2.5">
          {isProcessingAudio
            ? 'Analysing your voice tone...'
            : 'SentiMind AI is a supportive companion — not a replacement for professional clinical help.'}
        </p>
      </div>
    </div>
  )
}

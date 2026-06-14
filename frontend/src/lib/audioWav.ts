function writeString(view: DataView, offset: number, value: string) {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i))
  }
}

function floatTo16BitPCM(output: DataView, offset: number, input: Float32Array) {
  for (let i = 0; i < input.length; i += 1, offset += 2) {
    const sample = Math.max(-1, Math.min(1, input[i]))
    output.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
  }
}

function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const numSamples = samples.length
  const buffer = new ArrayBuffer(44 + numSamples * 2)
  const view = new DataView(buffer)

  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + numSamples * 2, true)
  writeString(view, 8, 'WAVE')
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(view, 36, 'data')
  view.setUint32(40, numSamples * 2, true)
  floatTo16BitPCM(view, 44, samples)

  return buffer
}

export async function blobToWavBase64(blob: Blob, targetSampleRate = 16000): Promise<string> {
  const arrayBuffer = await blob.arrayBuffer()
  const audioContext = new AudioContext({ sampleRate: targetSampleRate })
  const decoded = await audioContext.decodeAudioData(arrayBuffer)
  await audioContext.close()

  const mono = decoded.getChannelData(0)
  const wavBuffer = encodeWav(mono, targetSampleRate)
  const wavBlob = new Blob([wavBuffer], { type: 'audio/wav' })

  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.readAsDataURL(wavBlob)
    reader.onloadend = () => resolve(reader.result as string)
    reader.onerror = reject
  })
}

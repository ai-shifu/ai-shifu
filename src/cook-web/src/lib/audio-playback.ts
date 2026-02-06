export const createAudioContext = (): AudioContext => {
  if (typeof window === 'undefined') {
    throw new Error('AudioContext requires a browser environment.');
  }

  const AudioContextCtor =
    window.AudioContext ||
    (
      window as typeof window & {
        webkitAudioContext?: typeof AudioContext;
      }
    ).webkitAudioContext;

  if (!AudioContextCtor) {
    throw new Error('AudioContext is not supported in this browser.');
  }

  return new AudioContextCtor();
};

export const resumeAudioContext = async (
  audioContext: AudioContext,
): Promise<void> => {
  if (audioContext.state === 'suspended') {
    await audioContext.resume();
  }
};

export const decodeBase64ToArrayBuffer = (audioData: string): ArrayBuffer => {
  const binaryString = atob(audioData);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i += 1) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer.slice(0);
};

export const decodeAudioBufferFromBase64 = async (
  audioContext: AudioContext,
  audioData: string,
): Promise<AudioBuffer> => {
  const arrayBuffer = decodeBase64ToArrayBuffer(audioData);
  return audioContext.decodeAudioData(arrayBuffer);
};

export const playAudioBuffer = (
  audioContext: AudioContext,
  audioBuffer: AudioBuffer,
  onEnded?: () => void,
  startOffsetSeconds: number = 0,
): AudioBufferSourceNode => {
  const sourceNode = audioContext.createBufferSource();
  sourceNode.buffer = audioBuffer;
  sourceNode.connect(audioContext.destination);
  if (onEnded) {
    sourceNode.onended = onEnded;
  }
  const safeOffset = Number.isFinite(startOffsetSeconds)
    ? Math.max(0, startOffsetSeconds)
    : 0;
  const maxOffset = Math.max(0, audioBuffer.duration - 0.01);
  sourceNode.start(0, Math.min(safeOffset, maxOffset));
  return sourceNode;
};

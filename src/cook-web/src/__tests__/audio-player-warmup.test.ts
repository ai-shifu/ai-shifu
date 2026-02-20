const mockAudioContext = {
  state: 'suspended',
  resume: jest.fn(() => Promise.resolve()),
  suspend: jest.fn(() => Promise.resolve()),
  close: jest.fn(() => Promise.resolve()),
} as unknown as AudioContext;

const createAudioContextMock = jest.fn(() => mockAudioContext);
const resumeAudioContextMock = jest.fn(() => Promise.resolve());

jest.mock('@/lib/audio-playback', () => ({
  createAudioContext: (...args: unknown[]) => createAudioContextMock(...args),
  resumeAudioContext: (...args: unknown[]) => resumeAudioContextMock(...args),
  decodeAudioBufferFromBase64: jest.fn(),
  playAudioBuffer: jest.fn(),
}));

import { warmupSharedAudioPlayback } from '@/components/audio/AudioPlayer';

describe('AudioPlayer warmup', () => {
  beforeEach(() => {
    createAudioContextMock.mockClear();
    resumeAudioContextMock.mockClear();
  });

  it('reuses shared audio context across warmups', () => {
    warmupSharedAudioPlayback();
    warmupSharedAudioPlayback();

    expect(createAudioContextMock).toHaveBeenCalledTimes(1);
    expect(resumeAudioContextMock).toHaveBeenCalledTimes(2);
  });

  it('swallows warmup errors to keep interaction flow stable', () => {
    createAudioContextMock.mockImplementationOnce(() => {
      throw new Error('no-audio-context');
    });

    expect(() => warmupSharedAudioPlayback()).not.toThrow();
  });
});

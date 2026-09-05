import type { LiveVoiceFollowUpController } from './useLiveVoiceFollowUp';

export const mockLiveVoiceController = (
  overrides: Partial<LiveVoiceFollowUpController> = {},
): LiveVoiceFollowUpController => ({
  open: false,
  paused: false,
  state: 'ended',
  muted: true,
  warning: false,
  microphonePending: false,
  microphoneError: null,
  textPending: false,
  anchorElementBid: null,
  errorCode: null,
  retryable: false,
  retryAvailableAt: null,
  endReason: null,
  start: jest.fn(),
  startMicrophone: jest.fn(),
  stopMicrophone: jest.fn(),
  sendText: jest.fn().mockResolvedValue(true),
  retry: jest.fn(),
  toggleMuted: jest.fn(),
  end: jest.fn(),
  pause: jest.fn(),
  close: jest.fn(),
  ...overrides,
});

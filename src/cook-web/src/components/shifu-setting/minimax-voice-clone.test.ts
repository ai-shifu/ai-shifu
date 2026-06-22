import {
  buildMiniMaxClonedVoiceListParams,
  buildMiniMaxVoiceOptions,
  executeMiniMaxVoiceAction,
  getMiniMaxCloneSubmitBlockReason,
  getMiniMaxRecordingElapsedSeconds,
  isValidMiniMaxCustomVoiceId,
  loadMiniMaxVoiceRefreshData,
  shouldPreserveCustomMiniMaxVoice,
} from './minimax-voice-clone';

describe('minimax voice clone helpers', () => {
  it('validates local MiniMax custom voice ids', () => {
    expect(isValidMiniMaxCustomVoiceId('AiShifu_voice_123')).toBe(true);
    expect(isValidMiniMaxCustomVoiceId('1starts-with-digit')).toBe(false);
    expect(isValidMiniMaxCustomVoiceId('AiShifu_voice_')).toBe(false);
  });

  it('preserves unknown saved MiniMax custom voice ids', () => {
    expect(
      shouldPreserveCustomMiniMaxVoice({
        providerName: 'minimax',
        supportsCustomVoiceId: true,
        voiceId: 'AiShifu_saved_voice_1',
        builtInVoices: [{ value: 'male-qn-qingse', label: 'Male' }],
      }),
    ).toBe(true);
  });

  it('does not preserve unknown non-MiniMax voice ids', () => {
    expect(
      shouldPreserveCustomMiniMaxVoice({
        providerName: 'baidu',
        supportsCustomVoiceId: false,
        voiceId: 'AiShifu_saved_voice_1',
        builtInVoices: [{ value: 'baidu-voice', label: 'Baidu' }],
      }),
    ).toBe(false);
  });

  it('merges built-in, cloned, disabled, and manual voice options', () => {
    const options = buildMiniMaxVoiceOptions({
      builtInVoices: [{ value: 'male-qn-qingse', label: 'Male' }],
      clonedVoices: [
        {
          voice_bid: 'voice-1',
          voice_id: 'AiShifu_ready_voice',
          display_name: 'Ready Voice',
          status: 'ready',
          minimax_demo_audio_url: 'https://cdn.example.com/ready.mp3',
        },
        {
          voice_bid: 'voice-2',
          voice_id: 'AiShifu_processing_voice',
          display_name: 'Processing Voice',
          status: 'processing',
        },
      ],
      currentVoiceId: 'AiShifu_manual_voice',
      manualLabel: 'Manual custom voice',
      statusLabels: {
        processing: 'Processing',
      },
    });

    expect(options.map(option => option.value)).toEqual([
      'male-qn-qingse',
      'AiShifu_ready_voice',
      'AiShifu_processing_voice',
      'AiShifu_manual_voice',
    ]);
    expect(options[1]).toMatchObject({
      label: 'Ready Voice',
      source: 'cloned',
      disabled: false,
      voice_bid: 'voice-1',
      minimax_demo_audio_url: 'https://cdn.example.com/ready.mp3',
    });
    expect(options[2]).toMatchObject({
      source: 'cloned',
      disabled: true,
      status: 'processing',
    });
    expect(options[3]).toMatchObject({
      label: 'Manual custom voice (AiShifu_manual_voice)',
      source: 'manual',
      disabled: false,
    });
  });

  it('adds a manual option only for unknown current MiniMax custom voices', () => {
    const knownOptions = buildMiniMaxVoiceOptions({
      builtInVoices: [{ value: 'male-qn-qingse', label: 'Male' }],
      clonedVoices: [
        {
          voice_bid: 'voice-1',
          voice_id: 'AiShifu_ready_voice',
          display_name: 'Ready Voice',
          status: 'ready',
        },
      ],
      currentVoiceId: 'AiShifu_ready_voice',
      manualLabel: 'Manual custom voice',
    });

    expect(knownOptions.some(option => option.source === 'manual')).toBe(false);

    const unknownOptions = buildMiniMaxVoiceOptions({
      builtInVoices: [{ value: 'male-qn-qingse', label: 'Male' }],
      clonedVoices: [],
      currentVoiceId: 'AiShifu_unknown_voice',
      manualLabel: 'Manual custom voice',
    });

    expect(unknownOptions.at(-1)).toMatchObject({
      value: 'AiShifu_unknown_voice',
      label: 'Manual custom voice (AiShifu_unknown_voice)',
      source: 'manual',
      disabled: false,
    });
  });

  it('reports MiniMax voice action failures without running success callbacks', async () => {
    const onError = jest.fn();
    const onSuccess = jest.fn();

    const result = await executeMiniMaxVoiceAction({
      action: jest.fn().mockRejectedValue(new Error('retry failed')),
      onSuccess,
      onError,
    });

    expect(result).toBe(false);
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(new Error('retry failed'));
  });

  it('runs MiniMax voice action success callbacks after the action succeeds', async () => {
    const onError = jest.fn();
    const onSuccess = jest.fn();

    const result = await executeMiniMaxVoiceAction({
      action: jest.fn().mockResolvedValue(undefined),
      onSuccess,
      onError,
    });

    expect(result).toBe(true);
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it('keeps cloned voices when clone cost refresh fails', async () => {
    const readyVoice = {
      voice_bid: 'voice-1',
      voice_id: 'AiShifu_ready_voice',
      display_name: 'Ready Voice',
      status: 'ready',
    };

    const result = await loadMiniMaxVoiceRefreshData({
      fetchVoices: jest.fn().mockResolvedValue({ voices: [readyVoice] }),
      fetchCloneCost: jest
        .fn()
        .mockRejectedValue(new Error('clone cost unavailable')),
    });

    expect(result.voices).toEqual([readyVoice]);
    expect(result.cloneCost).toBeNull();
    expect(result.errors).toHaveLength(1);
  });

  it('requests owner-wide cloned voices without current shifu filtering', () => {
    expect(
      buildMiniMaxClonedVoiceListParams('3aab99292889400f9f3c935a45ab2b0e'),
    ).toEqual({});
  });

  it('allows clone submission once source recording is long enough', () => {
    expect(
      getMiniMaxCloneSubmitBlockReason({
        sourceFileSelected: true,
        sourceElapsed: 12,
        recordingKind: null,
        submitting: false,
        cloneInProgress: false,
        canSubmitByCredits: true,
      }),
    ).toBeNull();
  });

  it('uses ten recorded seconds as the hard source-audio submit gate', () => {
    expect(
      getMiniMaxCloneSubmitBlockReason({
        sourceFileSelected: true,
        sourceElapsed: 9,
        recordingKind: null,
        submitting: false,
        cloneInProgress: false,
        canSubmitByCredits: true,
      }),
    ).toBe('source_recording_too_short');

    expect(
      getMiniMaxCloneSubmitBlockReason({
        sourceFileSelected: true,
        sourceElapsed: 10,
        recordingKind: null,
        submitting: false,
        cloneInProgress: false,
        canSubmitByCredits: true,
      }),
    ).toBeNull();
  });

  it('does not round source recording duration up to the ten-second gate', () => {
    expect(getMiniMaxRecordingElapsedSeconds(1_000, 10_999)).toBe(9);
    expect(getMiniMaxRecordingElapsedSeconds(1_000, 11_000)).toBe(10);
    expect(getMiniMaxRecordingElapsedSeconds(1_000, 500)).toBe(0);
  });

  it('explains source audio submission blockers', () => {
    expect(
      getMiniMaxCloneSubmitBlockReason({
        sourceFileSelected: false,
        sourceElapsed: 0,
        recordingKind: null,
        submitting: false,
        cloneInProgress: false,
        canSubmitByCredits: true,
      }),
    ).toBe('missing_source_audio');

    expect(
      getMiniMaxCloneSubmitBlockReason({
        sourceFileSelected: true,
        sourceElapsed: 8,
        recordingKind: null,
        submitting: false,
        cloneInProgress: false,
        canSubmitByCredits: true,
      }),
    ).toBe('source_recording_too_short');
  });

  it('blocks duplicate submission while a clone job is polling', () => {
    expect(
      getMiniMaxCloneSubmitBlockReason({
        sourceFileSelected: true,
        sourceElapsed: 0,
        recordingKind: null,
        submitting: false,
        cloneInProgress: true,
        canSubmitByCredits: true,
      }),
    ).toBe('clone_in_progress');
  });
});

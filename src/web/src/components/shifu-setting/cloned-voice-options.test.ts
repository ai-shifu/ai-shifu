import {
  buildClonedVoiceListParams,
  buildMiniMaxVoiceOptions,
  isValidMiniMaxCustomVoiceId,
  isValidVolcengineCustomVoiceId,
  providerSupportsClonedVoices,
  shouldPreserveCustomMiniMaxVoice,
} from './cloned-voice-options';

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

  it('merges cloned, built-in, disabled, and manual voice options', () => {
    const options = buildMiniMaxVoiceOptions({
      builtInVoices: [{ value: 'male-qn-qingse', label: 'Male' }],
      clonedVoices: [
        {
          voice_bid: 'voice-1',
          voice_id: 'AiShifu_ready_voice',
          display_name: 'Teacher',
          status: 'ready',
        },
        {
          voice_bid: 'voice-2',
          voice_id: 'AiShifu_processing_voice',
          display_name: 'Assistant',
          status: 'processing',
        },
      ],
      currentVoiceId: 'AiShifu_manual_voice',
      clonedVoiceLabelFormatter: name => `${name} 语音clone 音色`,
      manualLabel: 'Manual custom voice',
      statusLabels: {
        processing: 'Processing',
      },
    });

    expect(options.map(option => option.value)).toEqual([
      'AiShifu_ready_voice',
      'AiShifu_processing_voice',
      'male-qn-qingse',
      'AiShifu_manual_voice',
    ]);
    expect(options[0]).toMatchObject({
      label: 'Teacher 语音clone 音色',
      source: 'cloned',
      disabled: false,
      voice_bid: 'voice-1',
    });
    expect(options[1]).toMatchObject({
      label: 'Assistant 语音clone 音色 · Processing',
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

  it('keeps built-in voices selectable when cloned voice ids collide', () => {
    const options = buildMiniMaxVoiceOptions({
      builtInVoices: [{ value: 'male-qn-qingse', label: 'Male built-in' }],
      clonedVoices: [
        {
          voice_bid: 'voice-collide-1',
          voice_id: 'male-qn-qingse',
          display_name: 'Failed clone using built-in id',
          status: 'failed',
        },
        {
          voice_bid: 'voice-ready-1',
          voice_id: 'AiShifu_ready_voice',
          display_name: 'Ready Voice',
          status: 'ready',
        },
      ],
      currentVoiceId: '',
      manualLabel: 'Manual custom voice',
    });

    expect(options.map(option => option.value)).toEqual([
      'AiShifu_ready_voice',
      'male-qn-qingse',
    ]);
    expect(options[1]).toMatchObject({
      label: 'Male built-in',
      source: 'built_in',
      disabled: false,
    });
    expect(options.some(option => option.voice_bid === 'voice-collide-1')).toBe(
      false,
    );
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

  it('requests owner-wide cloned voices without current shifu filtering', () => {
    expect(
      buildClonedVoiceListParams('minimax', '3aab99292889400f9f3c935a45ab2b0e'),
    ).toEqual({ provider: 'minimax' });
    expect(buildClonedVoiceListParams('')).toEqual({});
  });

  it('validates volcengine speaker ids and provider cloning support', () => {
    expect(isValidVolcengineCustomVoiceId('S_xxxxxxxxxx')).toBe(true);
    expect(isValidVolcengineCustomVoiceId('AiShifu_voice_123')).toBe(false);
    expect(isValidVolcengineCustomVoiceId('s_lowercase1')).toBe(false);

    expect(providerSupportsClonedVoices('minimax')).toBe(true);
    expect(providerSupportsClonedVoices('volcengine')).toBe(true);
    expect(providerSupportsClonedVoices('volcengine_http')).toBe(false);
    expect(providerSupportsClonedVoices('baidu')).toBe(false);
  });

  it('lists volcengine cloned voices alongside built-ins without model tags', () => {
    const options = buildMiniMaxVoiceOptions({
      builtInVoices: [{ value: 'zh_female_vv_uranus_bigtts', label: 'Vivi' }],
      clonedVoices: [
        {
          voice_bid: 'vb-volc-1',
          voice_id: 'S_xxxxxxxxxx',
          display_name: '何老师的声音',
          provider: 'volcengine',
          status: 'ready',
        },
      ],
      currentVoiceId: 'S_xxxxxxxxxxxxxxxxx',
      manualLabel: 'Manual',
      manualVoiceValidator: isValidVolcengineCustomVoiceId,
    });

    const cloned = options.find(option => option.value === 'S_xxxxxxxxxx');
    const manual = options.find(
      option => option.value === 'S_xxxxxxxxxxxxxxxxx',
    );
    expect(cloned?.source).toBe('cloned');
    // No resource_id annotation: cloned voices stay visible under the
    // teacher's normal model; the clone resource is inferred backend-side.
    expect(cloned?.resource_id).toBeUndefined();
    expect(manual?.source).toBe('manual');
    // A MiniMax-shaped current voice id must not survive the volcengine
    // manual validator.
    const rejected = buildMiniMaxVoiceOptions({
      builtInVoices: [],
      clonedVoices: [],
      currentVoiceId: 'AiShifu_saved_voice_1',
      manualLabel: 'Manual',
      manualVoiceValidator: isValidVolcengineCustomVoiceId,
    });
    expect(rejected).toHaveLength(0);
  });
});

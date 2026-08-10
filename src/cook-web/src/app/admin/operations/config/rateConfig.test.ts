import {
  buildCreateRatePayload,
  canonicalizeRateIdentity,
  deriveCreditsPerUnit,
  getRateDisplayName,
  getRateRowKey,
  hasExactRateIdentity,
  isRateRowCreateSuggestion,
  isValidProvider,
  isValidRateModel,
  normalizeMultiplierInput,
  type RateRow,
} from './rateConfig';

const rateRow = (overrides: Partial<RateRow>): RateRow =>
  ({
    usage_type: 'llm',
    usage_type_code: 7401,
    provider: 'qwen',
    model: 'qwen/deepseek-v4-flash',
    rate_model: 'deepseek-v4-flash',
    display_name: 'DeepSeek V4 Flash',
    usage_scene: 'production',
    usage_scene_code: 7411,
    billing_metric: 'llm_output_tokens',
    billing_metric_code: 7453,
    unit_size: 1,
    credits_per_unit: 0,
    unit_cost: 0,
    multiplier: null,
    rounding_mode: 7461,
    status_code: 0,
    source: 'unconfigured',
    ...overrides,
  }) as RateRow;

describe('rate config helpers', () => {
  test('encodes row-key fields without delimiter collisions', () => {
    const left = rateRow({
      usage_type: 'llm',
      provider: 'a-b',
      rate_model: 'c',
      billing_metric: 'metric',
    });
    const right = rateRow({
      usage_type: 'llm',
      provider: 'a',
      rate_model: 'b-c',
      billing_metric: 'metric',
    });

    expect(getRateRowKey(left)).not.toBe(getRateRowKey(right));
    expect(JSON.parse(getRateRowKey(left))).toEqual([
      'llm',
      'a-b',
      'c',
      'metric',
    ]);
  });

  test('keeps empty and special row-key fields stable', () => {
    const row = rateRow({
      usage_type: '',
      provider: 'provider,-[]"',
      model: 'ignored-model',
      rate_model: '',
      billing_metric: 'metric\n:-',
    });

    expect(getRateRowKey(row)).toBe(getRateRowKey({ ...row }));
    expect(JSON.parse(getRateRowKey(row))).toEqual([
      '',
      'provider,-[]"',
      '',
      'metric\n:-',
    ]);
    expect(
      JSON.parse(
        getRateRowKey(
          rateRow({ rate_model: undefined, model: 'fallback/model' }),
        ),
      )[2],
    ).toBe('fallback/model');
  });

  test('normalizes multiplier input with the existing two-decimal rule', () => {
    expect(normalizeMultiplierInput('１。234abc')).toBe('0.23');
    expect(normalizeMultiplierInput('1．25')).toBe('1.25');
    expect(normalizeMultiplierInput('1,5')).toBe('1.5');
  });

  test('canonicalizes LLM and provider-default TTS identities', () => {
    expect(
      canonicalizeRateIdentity('llm', ' qwen ', 'qwen/deepseek-v4-flash '),
    ).toEqual({
      usageType: 'llm',
      provider: 'qwen',
      model: 'qwen/deepseek-v4-flash',
      rateModel: 'deepseek-v4-flash',
    });
    expect(canonicalizeRateIdentity('tts', ' tencent ', ' ')).toEqual({
      usageType: 'tts',
      provider: 'tencent',
      model: '',
      rateModel: '',
    });
  });

  test('localizes only synthesized TTS default-tier display names', () => {
    expect(
      getRateDisplayName(
        rateRow({
          usage_type: 'tts',
          provider: 'tencent',
          model: '',
          rate_model: '',
          display_name: 'tencent',
        }),
        '默认档位',
      ),
    ).toBe('tencent/默认档位');
    expect(
      getRateDisplayName(
        rateRow({
          usage_type: 'tts',
          provider: 'tencent',
          model: '',
          rate_model: '',
          display_name: 'tencent/default',
        }),
        '默认档位',
      ),
    ).toBe('tencent/默认档位');
    expect(
      getRateDisplayName(
        rateRow({
          usage_type: 'tts',
          provider: 'tencent',
          model: '',
          rate_model: '',
          display_name: 'Tencent Premium',
        }),
        '默认档位',
      ),
    ).toBe('Tencent Premium');
  });

  test('derives credits and builds the create-only payload', () => {
    const identity = canonicalizeRateIdentity(
      'llm',
      'qwen',
      'deepseek-v4-flash',
    );
    const creditsPerUnit = deriveCreditsPerUnit({
      usageType: 'llm',
      multiplier: '1.5',
      baseline: { is_configured: true, unit_cost: 0.000066667 },
    });

    expect(creditsPerUnit).toBe(0.0001000005);
    expect(
      buildCreateRatePayload({ identity, creditsPerUnit: creditsPerUnit! }),
    ).toEqual({
      create_only: true,
      usage_type: 'llm',
      provider: 'qwen',
      model: 'qwen/deepseek-v4-flash',
      rate_model: 'deepseek-v4-flash',
      billing_metric: 'llm_output_tokens',
      unit_size: 1,
      credits_per_unit: 0.0001000005,
      status: 'active',
    });
  });

  test('applies the TTS character factor and accepts a blank default tier', () => {
    const identity = canonicalizeRateIdentity('tts', 'tencent', '');
    const creditsPerUnit = deriveCreditsPerUnit({
      usageType: 'tts',
      multiplier: '2',
      baseline: {
        is_configured: true,
        unit_cost: 0.25,
        tts_chars_per_llm_token: 0.5,
      },
    });

    expect(creditsPerUnit).toBe(1);
    expect(
      buildCreateRatePayload({ identity, creditsPerUnit: creditsPerUnit! }),
    ).toEqual(
      expect.objectContaining({
        model: '',
        rate_model: '',
        billing_metric: 'tts_output_chars',
      }),
    );
    expect(isValidRateModel('tts', '')).toBe(true);
    expect(
      deriveCreditsPerUnit({
        usageType: 'tts',
        multiplier: '2',
        baseline: { is_configured: true, unit_cost: 0.25 },
      }),
    ).toBeNull();
    expect(
      deriveCreditsPerUnit({
        usageType: 'llm',
        multiplier: '2',
        baseline: { is_configured: false, unit_cost: 0.25 },
      }),
    ).toBeNull();
  });

  test('compares matched raw identities without canonicalizing aliases', () => {
    const identity = canonicalizeRateIdentity('llm', 'qwen', 'foo');
    const aliasBackedRow = rateRow({
      provider: 'qwen',
      model: 'qwen/foo',
      rate_model: 'foo',
      source: 'exact',
      matched_rate_provider: 'qwen',
      matched_rate_model: 'qwen/foo',
    });
    const rawExactRow = rateRow({
      provider: 'qwen',
      model: 'qwen/foo',
      rate_model: 'foo',
      source: 'exact',
      matched_rate_provider: 'qwen',
      matched_rate_model: 'foo',
    });

    expect(hasExactRateIdentity([aliasBackedRow], identity)).toBe(false);
    expect(hasExactRateIdentity([rawExactRow], identity)).toBe(true);
    expect(
      hasExactRateIdentity(
        [
          rateRow({
            usage_type: 'tts',
            provider: 'custom-tts',
            model: '',
            rate_model: '',
            source: 'exact',
            matched_rate_provider: 'custom-tts',
            matched_rate_model: '',
          }),
        ],
        canonicalizeRateIdentity('tts', 'custom-tts', ''),
      ),
    ).toBe(true);
    expect(
      hasExactRateIdentity(
        [
          rateRow({
            ...rawExactRow,
            matched_rate_provider: null,
            matched_rate_model: null,
          }),
        ],
        identity,
      ),
    ).toBe(false);
    expect(isRateRowCreateSuggestion(aliasBackedRow, 'llm')).toBe(true);
    expect(isRateRowCreateSuggestion(rawExactRow, 'llm')).toBe(false);
    expect(
      isRateRowCreateSuggestion(
        rateRow({ ...rawExactRow, display_name: 'DB-only exact rate' }),
        'llm',
      ),
    ).toBe(false);
  });

  test('falls back to legacy source identity only when matched fields are missing', () => {
    const identity = canonicalizeRateIdentity('llm', 'qwen', 'foo');

    expect(
      hasExactRateIdentity(
        [
          rateRow({
            source: 'exact',
            provider: 'qwen',
            model: 'qwen/foo',
            rate_model: 'foo',
          }),
        ],
        identity,
      ),
    ).toBe(true);
    expect(
      hasExactRateIdentity(
        [
          rateRow({
            source: 'default',
            provider: 'qwen',
            model: 'qwen/foo',
            rate_model: 'foo',
          }),
        ],
        identity,
      ),
    ).toBe(false);
    expect(
      hasExactRateIdentity(
        [
          rateRow({
            source: 'exact',
            provider: 'qwen',
            model: 'qwen/foo',
            rate_model: 'foo',
            matched_rate_provider: 'qwen',
          }),
        ],
        identity,
      ),
    ).toBe(false);
  });

  test('rejects wildcard and control characters in exact identities', () => {
    expect(isValidProvider('qw*en')).toBe(false);
    expect(isValidProvider('qw\nen')).toBe(false);
    expect(isValidRateModel('llm', 'model*')).toBe(false);
    expect(isValidRateModel('llm', '')).toBe(false);
  });
});

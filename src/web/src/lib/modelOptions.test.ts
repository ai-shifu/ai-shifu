import {
  normalizeModelOptionMetadata,
  normalizeModelOptions,
} from './modelOptions';

describe('normalizeModelOptionMetadata', () => {
  test.each([0, -1, null, undefined, '', 'invalid', Infinity, NaN])(
    'omits a multiplier badge for the invalid rate %s',
    credit_multiplier => {
      expect(normalizeModelOptionMetadata({ credit_multiplier })).toEqual({
        creditMultiplier: null,
        creditMultiplierLabel: '',
        isDefault: false,
      });
    },
  );

  test('rounds numeric API strings up and trims display labels', () => {
    expect(
      normalizeModelOptionMetadata({
        creditMultiplier: '2.2',
        creditMultiplierLabel: ' 3x ',
        isDefault: true,
      }),
    ).toEqual({
      creditMultiplier: 3,
      creditMultiplierLabel: '3x',
      isDefault: true,
    });
  });

  test('preserves explicit zero and false snake-case values over aliases', () => {
    expect(
      normalizeModelOptionMetadata({
        credit_multiplier: 0,
        creditMultiplier: 3,
        credit_multiplier_label: ' ',
        creditMultiplierLabel: '3x',
        is_default: false,
        isDefault: true,
      }),
    ).toEqual({
      creditMultiplier: null,
      creditMultiplierLabel: '',
      isDefault: false,
    });
  });

  test('falls back to aliases for nullish rates and empty labels', () => {
    expect(
      normalizeModelOptionMetadata({
        credit_multiplier: null,
        creditMultiplier: 0.5,
        credit_multiplier_label: '',
        creditMultiplierLabel: ' 1x ',
        is_default: null,
        isDefault: true,
      }),
    ).toEqual({
      creditMultiplier: 1,
      creditMultiplierLabel: '1x',
      isDefault: true,
    });
  });
});

describe('normalizeModelOptions', () => {
  test('keeps the first normalized model and legacy string option shape', () => {
    expect(
      normalizeModelOptions([
        ' model-a ',
        { model: 'model-a', label: 'Duplicate', credit_multiplier: 3 },
        null,
        '',
        {},
        { value: ' model-b ', displayName: ' Model B ' },
      ]),
    ).toEqual([
      { value: 'model-a', label: 'model-a' },
      {
        value: 'model-b',
        label: 'Model B',
        creditMultiplier: null,
        creditMultiplierLabel: '',
        isDefault: false,
      },
    ]);
    expect(normalizeModelOptions(null)).toEqual([]);
  });

  test('keeps API credit multipliers without changing display labels', () => {
    expect(
      normalizeModelOptions([
        {
          model: 'qwen/deepseek-v4-flash',
          display_name: 'DeepSeek-V4-Flash',
          credit_multiplier: 1,
          is_default: true,
        },
        {
          model: 'ark/doubao-seed-2-0-lite-260428',
          display_name: 'Doubao-Seed-2.0-lite',
          creditMultiplier: 2.2,
          creditMultiplierLabel: '3x',
        },
        {
          model: 'qwen/no-rate-model',
          display_name: 'No Rate',
          credit_multiplier: null,
        },
      ]),
    ).toEqual([
      {
        value: 'qwen/deepseek-v4-flash',
        label: 'DeepSeek-V4-Flash',
        creditMultiplier: 1,
        creditMultiplierLabel: '',
        isDefault: true,
      },
      {
        value: 'ark/doubao-seed-2-0-lite-260428',
        label: 'Doubao-Seed-2.0-lite',
        creditMultiplier: 3,
        creditMultiplierLabel: '3x',
        isDefault: false,
      },
      {
        value: 'qwen/no-rate-model',
        label: 'No Rate',
        creditMultiplier: null,
        creditMultiplierLabel: '',
        isDefault: false,
      },
    ]);
  });
});

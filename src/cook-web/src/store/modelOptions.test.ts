import { normalizeModelOptions } from './modelOptions';

describe('normalizeModelOptions', () => {
  test('keeps API credit multipliers without changing display labels', () => {
    expect(
      normalizeModelOptions([
        {
          model: 'qwen/deepseek-v4-flash',
          display_name: 'DeepSeek-V4-Flash',
          credit_multiplier: 1,
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
      },
      {
        value: 'ark/doubao-seed-2-0-lite-260428',
        label: 'Doubao-Seed-2.0-lite',
        creditMultiplier: 3,
        creditMultiplierLabel: '3x',
      },
      {
        value: 'qwen/no-rate-model',
        label: 'No Rate',
        creditMultiplier: null,
        creditMultiplierLabel: '',
      },
    ]);
  });
});

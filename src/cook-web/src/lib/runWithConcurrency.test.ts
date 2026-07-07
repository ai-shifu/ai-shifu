import { runWithConcurrency } from './runWithConcurrency';

describe('runWithConcurrency', () => {
  it('returns results index-aligned to the input order', async () => {
    const items = [1, 2, 3, 4, 5];
    const results = await runWithConcurrency(items, 2, async n => n * 10);
    expect(results).toEqual([10, 20, 30, 40, 50]);
  });

  it('never exceeds the concurrency limit', async () => {
    let active = 0;
    let maxActive = 0;
    const items = Array.from({ length: 12 }, (_, i) => i);

    await runWithConcurrency(items, 3, async i => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise(resolve => setTimeout(resolve, 5));
      active -= 1;
      return i;
    });

    expect(maxActive).toBeLessThanOrEqual(3);
  });

  it('records null for a rejected worker without aborting the batch', async () => {
    const items = [1, 2, 3, 4];
    const results = await runWithConcurrency(items, 2, async n => {
      if (n === 2) {
        throw new Error('boom');
      }
      return n;
    });
    expect(results).toEqual([1, null, 3, 4]);
  });

  it('handles an empty list', async () => {
    const results = await runWithConcurrency([], 3, async n => n);
    expect(results).toEqual([]);
  });

  it('clamps limits below 1 to a single worker', async () => {
    let active = 0;
    let maxActive = 0;
    const items = [1, 2, 3];
    await runWithConcurrency(items, 0, async i => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise(resolve => setTimeout(resolve, 1));
      active -= 1;
      return i;
    });
    expect(maxActive).toBe(1);
  });
});

/**
 * Run an async `worker` over `items` with a bounded number of concurrent tasks.
 *
 * Uses a dynamic worker pool (complete one, start the next) rather than fixed
 * batches, so the pool stays saturated and there is no barrier between chunks.
 *
 * Guarantees:
 * - At most `limit` workers run at any time.
 * - Results are returned index-aligned to `items` (order preserved).
 * - A rejected worker yields `null` for that slot and never aborts the batch.
 */
export async function runWithConcurrency<T, R>(
  items: readonly T[],
  limit: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<(R | null)[]> {
  const results: (R | null)[] = new Array(items.length).fill(null);
  if (items.length === 0) {
    return results;
  }

  const effectiveLimit = Math.max(1, Math.min(Math.floor(limit) || 1, items.length));
  let nextIndex = 0;

  const runOne = async (): Promise<void> => {
    // Each runner pulls the next unclaimed index until the queue drains.
    for (;;) {
      const current = nextIndex;
      nextIndex += 1;
      if (current >= items.length) {
        return;
      }
      try {
        results[current] = await worker(items[current], current);
      } catch {
        results[current] = null;
      }
    }
  };

  const runners = Array.from({ length: effectiveLimit }, () => runOne());
  await Promise.all(runners);
  return results;
}

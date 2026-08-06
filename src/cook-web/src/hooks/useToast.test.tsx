import { act } from '@testing-library/react';
import { toast, toastOnce } from './useToast';

describe('toastOnce', () => {
  afterEach(() => {
    act(() => {
      toast({ title: 'cleanup', duration: 0 }).dismiss();
    });
  });

  it('suppresses duplicates while the previous toast is still visible', () => {
    const first = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'first',
      duration: 0,
    });
    const second = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'second',
      duration: 0,
    });

    expect(second.id).toBe(first.id);
  });

  it('re-shows a deduped toast after the previous toast is dismissed', () => {
    const first = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'first',
      duration: 0,
    });

    act(() => {
      first.dismiss();
    });

    const second = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'second',
      duration: 0,
    });

    expect(second.id).not.toBe(first.id);
  });

  it('re-shows a deduped toast after another toast replaces the previous one', () => {
    const first = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'first',
      duration: 0,
    });

    toast({ title: 'replacement', duration: 0 });

    const second = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'second',
      duration: 0,
    });

    expect(second.id).not.toBe(first.id);
  });
});

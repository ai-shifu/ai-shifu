type RegenerateResult = 'success' | 'failed' | 'cancelled';
type TrackEvent = (name: string, payload: Record<string, unknown>) => unknown;

/** Track one admitted Debug regeneration without collecting the selected step. */
export function startDebugRegenerateTracking({
  anchor,
  shifuBid,
  outlineBid,
  trackEvent,
}: {
  anchor?: string;
  shifuBid: string;
  outlineBid: string;
  trackEvent: TrackEvent;
}): ((result: RegenerateResult) => void) | undefined {
  if (!anchor) return;
  const payload = {
    shifu_bid: shifuBid,
    outline_bid: outlineBid,
  };
  const emit = (name: string, data: Record<string, unknown>) => {
    try {
      void Promise.resolve(trackEvent(name, data)).catch(() => {});
    } catch {}
  };
  emit('teacher_debug_regenerate_start', payload);
  let finished = false;
  return result => {
    if (finished) return;
    finished = true;
    emit('teacher_debug_regenerate_result', { ...payload, result });
  };
}

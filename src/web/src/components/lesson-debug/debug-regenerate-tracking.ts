type RegenerateResult = 'success' | 'failed' | 'cancelled';
type TrackEvent = (name: string, payload: Record<string, unknown>) => unknown;

/** Track one admitted Debug regeneration without collecting the selected step. */
export function startDebugRegenerateTracking({
  anchor,
  answerEdit = false,
  shifuBid,
  outlineBid,
  trackEvent,
}: {
  anchor?: string;
  answerEdit?: boolean;
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
  const family = answerEdit
    ? 'teacher_debug_answer_edit'
    : 'teacher_debug_regenerate';
  emit(`${family}_start`, payload);
  let finished = false;
  return result => {
    if (finished) return;
    finished = true;
    emit(`${family}_result`, { ...payload, result });
  };
}

type AnswerEditResult = 'success' | 'failed' | 'cancelled';
type TrackEvent = (name: string, payload: Record<string, unknown>) => unknown;

/** Track one admitted Debug answer edit without collecting the selected step. */
export function startDebugAnswerEditTracking({
  anchor,
  shifuBid,
  outlineBid,
  trackEvent,
}: {
  anchor?: string;
  shifuBid: string;
  outlineBid: string;
  trackEvent: TrackEvent;
}): ((result: AnswerEditResult) => void) | undefined {
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
  const family = 'teacher_debug_answer_edit';
  emit(`${family}_start`, payload);
  let finished = false;
  return result => {
    if (finished) return;
    finished = true;
    emit(`${family}_result`, { ...payload, result });
  };
}

type RetakeOutcome = 'success' | 'failed';
type TrackEvent = (name: string, payload: Record<string, unknown>) => unknown;

/** Measure one accepted recommended retake without affecting the operation. */
export function startLessonUpdateRetakeTracking({
  shifuBid,
  outlineBid,
  previewMode,
  trackEvent,
}: {
  shifuBid: string;
  outlineBid: string;
  previewMode: boolean;
  trackEvent: TrackEvent;
}): ((outcome: RetakeOutcome) => void) | undefined {
  if (!shifuBid.trim() || !outlineBid.trim()) return;

  const payload = {
    shifu_bid: shifuBid,
    outline_bid: outlineBid,
    surface: previewMode ? 'teacher_preview' : 'published_learning',
  };
  const emit = (name: string, data: Record<string, unknown>) => {
    try {
      void Promise.resolve(trackEvent(name, data)).catch(() => {});
    } catch {}
  };
  emit('lesson_update_retake_attempt', payload);

  let finished = false;
  return outcome => {
    if (finished) return;
    finished = true;
    emit('lesson_update_retake_result', { ...payload, outcome });
  };
}

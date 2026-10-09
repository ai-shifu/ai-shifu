type RewindResult = 'success' | 'failed' | 'cancelled';
type TrackEvent = (name: string, payload: Record<string, unknown>) => unknown;

/** Track one initiated draft rewind without affecting its stream or collecting input. */
export function startPreviewRewindTracking({
  preview,
  anchor,
  answering,
  shifuBid,
  outlineBid,
  learningMode,
  trackEvent,
}: {
  preview: boolean;
  anchor?: string;
  answering: boolean;
  shifuBid: string;
  outlineBid: string;
  learningMode: string;
  trackEvent: TrackEvent;
}): ((result: RewindResult) => void) | undefined {
  if (!preview || !anchor) return;
  const payload = {
    shifu_bid: shifuBid,
    outline_bid: outlineBid,
    operation: answering ? 'answer_edit' : 'regenerate',
    learning_mode: learningMode === 'listen' ? 'listen' : 'read',
  };
  const emit = (name: string, data: Record<string, unknown>) => {
    try {
      void Promise.resolve(trackEvent(name, data)).catch(() => {});
    } catch {}
  };
  emit('teacher_preview_rewind_start', payload);
  let finished = false;
  return result => {
    if (finished) return;
    finished = true;
    emit('teacher_preview_rewind_result', { ...payload, result });
  };
}

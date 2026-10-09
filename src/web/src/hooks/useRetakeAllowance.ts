import { useEffect, useRef, useState } from 'react';
import { getRetakeStatus, type RetakeStatus } from '@/api/retake';
import { useEnvStore } from '@/store/envStore';
import { useSystemStore } from '@/store/useSystemStore';
import { useTracking } from '@/hooks/useTracking';

export function useRetakeAllowance(
  open: boolean,
  lessonId: string | undefined,
  entry: 'catalog' | 'update',
  prefetch = false,
) {
  const courseId = useEnvStore(state => state.courseId);
  const preview = useSystemStore(state => state.previewMode);
  const { trackEvent } = useTracking();
  const trackRef = useRef(trackEvent);
  trackRef.current = trackEvent;
  const [response, setResponse] = useState<{
    key: string;
    status?: RetakeStatus;
    failed?: boolean;
  }>();
  const noticeStates = useRef(new Set<string>());
  const key = `${courseId}:${lessonId}:${preview}`;
  useEffect(() => {
    setResponse(undefined);
    if ((!open && !prefetch) || preview || !lessonId) return;
    let active = true;
    getRetakeStatus(courseId, lessonId)
      .then(status => {
        if (!active) return;
        setResponse({ key, status });
        if (status.available && !status.quota_exempt) {
          const state = status.in_progress
            ? 'busy'
            : status.allowed
              ? 'available'
              : 'exhausted';
          const noticeKey = `${key}:${state}`;
          if (!open && noticeStates.current.has(noticeKey)) return;
          if (!open) noticeStates.current.add(noticeKey);
          try {
            void Promise.resolve(
              trackRef.current(
                open
                  ? 'learner_retake_admission_checked'
                  : 'learner_lesson_update_notice_shown',
                {
                  shifu_bid: courseId,
                  outline_bid: lessonId,
                  ...(open ? { entry } : {}),
                  state,
                },
              ),
            ).catch(() => {});
          } catch {}
        }
      })
      .catch(() => {
        if (active) setResponse({ key, failed: true });
      });
    return () => {
      active = false;
    };
  }, [open, preview, lessonId, courseId, entry, key, prefetch]);
  const current = response?.key === key ? response : undefined;
  const status = current?.status;
  const blocked =
    !preview && (!status || (status.available && !status.allowed));
  const result = (success: boolean) => {
    if (preview || !status?.available || status.quota_exempt) return;
    try {
      void Promise.resolve(
        trackRef.current('learner_retake_reset_result', {
          shifu_bid: courseId,
          outline_bid: lessonId,
          entry,
          result: success ? 'success' : 'failed',
        }),
      ).catch(() => {});
    } catch {}
  };
  return {
    status,
    blocked,
    loading: !preview && !current,
    failed: current?.failed,
    result,
  };
}

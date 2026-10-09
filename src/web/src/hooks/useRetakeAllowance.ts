import { useEffect, useRef, useState } from 'react';
import { getRetakeStatus, type RetakeStatus } from '@/api/retake';
import { useEnvStore } from '@/store/envStore';
import { useSystemStore } from '@/store/useSystemStore';
import { useUserStore } from '@/store/useUserStore';
import { useTracking } from '@/hooks/useTracking';

export function useRetakeAllowance(
  open: boolean,
  lessonId: string | undefined,
  entry: 'catalog' | 'update',
  prefetch = false,
) {
  const courseId = useEnvStore(state => state.courseId);
  const preview = useSystemStore(state => state.previewMode);
  const userId = useUserStore(state => state.userInfo?.user_id);
  const [refresh, setRefresh] = useState(0);
  const { trackEvent } = useTracking();
  const trackRef = useRef(trackEvent);
  trackRef.current = trackEvent;
  const [response, setResponse] = useState<{
    key: string;
    status?: RetakeStatus;
    failed?: boolean;
  }>();
  const noticeStates = useRef(new Set<string>());
  const checkedOpen = useRef<string | undefined>(undefined);
  const key = `${userId}:${courseId}:${lessonId}:${preview}`;
  useEffect(() => {
    if ((!open && !prefetch) || preview || !lessonId) return;
    const refreshStatus = () => setRefresh(value => value + 1);
    const refreshVisible = () => {
      if (document.visibilityState === 'visible') refreshStatus();
    };
    window.addEventListener('focus', refreshStatus);
    window.addEventListener('online', refreshStatus);
    document.addEventListener('visibilitychange', refreshVisible);
    return () => {
      window.removeEventListener('focus', refreshStatus);
      window.removeEventListener('online', refreshStatus);
      document.removeEventListener('visibilitychange', refreshVisible);
    };
  }, [open, prefetch, preview, lessonId]);
  useEffect(() => {
    setResponse(undefined);
    if ((!open && !prefetch) || preview || !lessonId) return;
    let active = true;
    getRetakeStatus(courseId, lessonId)
      .then(status => {
        if (!active) return;
        setResponse({ key, status });
      })
      .catch(() => {
        if (active) setResponse({ key, failed: true });
      });
    return () => {
      active = false;
    };
  }, [open, preview, lessonId, courseId, entry, key, prefetch, refresh]);
  const current = response?.key === key ? response : undefined;
  const status = current?.status;
  useEffect(() => {
    if (!open) checkedOpen.current = undefined;
    if (preview || !status?.available || status.quota_exempt) return;
    const state = status.in_progress
      ? 'busy'
      : status.allowed
        ? 'available'
        : 'exhausted';
    const noticeKey = `${key}:${state}`;
    if (open) {
      if (checkedOpen.current === key) return;
      checkedOpen.current = key;
    } else {
      if (!prefetch || noticeStates.current.has(noticeKey)) return;
      noticeStates.current.add(noticeKey);
    }
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
  }, [open, preview, prefetch, status, key, courseId, lessonId, entry]);
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

import { useCallback, useEffect, useRef, useState } from 'react';
import { getLessonResetStatus } from '@/api/lesson';
import { useEnvStore } from '@/store/envStore';
import { useSystemStore } from '@/store/useSystemStore';
import { useUserStore } from '@/store/useUserStore';
import { useCourseStore } from '@/store/useCourseStore';

export type LessonResetPhase =
  | 'idle'
  | 'checking'
  | 'ready'
  | 'exhausted'
  | 'unavailable';

export const useLessonResetStatus = (
  lessonId: string | undefined,
  active: boolean,
) => {
  const courseId = useEnvStore(state => state.courseId);
  const preview = useSystemStore(state => state.previewMode);
  const userId = useUserStore(state => state.userInfo?.user_id);
  const initialized = useUserStore(state => state.isInitialized);
  const resetting = useCourseStore(
    state => state.resettingLessonId === lessonId,
  );
  const scope = JSON.stringify([courseId, lessonId, userId, preview]);
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const requestVersion = useRef(0);
  const [status, setStatus] = useState<{
    scope: string;
    phase: LessonResetPhase;
  }>({ scope, phase: 'idle' });
  const phase = status.scope === scope ? status.phase : 'idle';

  const refresh = useCallback(async (): Promise<LessonResetPhase> => {
    if (!initialized || !userId || !courseId || !lessonId) return 'idle';
    const version = ++requestVersion.current;
    setStatus({ scope, phase: 'checking' });
    let next: LessonResetPhase;
    try {
      const result = await getLessonResetStatus(lessonId);
      next =
        result.can_reset === true
          ? 'ready'
          : result.can_reset === false
            ? 'exhausted'
            : 'unavailable';
    } catch {
      next = 'unavailable';
    }
    if (currentScope.current !== scope || version !== requestVersion.current)
      return 'idle';
    setStatus({ scope, phase: next });
    return next;
  }, [courseId, initialized, lessonId, scope, userId]);

  useEffect(() => {
    if (active && !resetting) void refresh();
    return () => {
      requestVersion.current += 1;
    };
  }, [active, refresh, resetting]);

  const setFailure = useCallback(
    (error: unknown) => {
      const code = (error as { code?: number } | null)?.code;
      if (code === 4021 || code === 4022) {
        setStatus({
          scope,
          phase: code === 4021 ? 'exhausted' : 'unavailable',
        });
      }
    },
    [scope],
  );

  return { phase, refresh, setFailure };
};

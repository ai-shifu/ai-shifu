import { useCallback, useEffect, useRef, useState } from 'react';
import { getLessonResetStatus } from '@/api/lesson';
import { useEnvStore } from '@/store/envStore';
import { useSystemStore } from '@/store/useSystemStore';
import { useUserStore } from '@/store/useUserStore';
import { useCourseStore } from '@/store/useCourseStore';

export const LESSON_RESET_LIMIT_REACHED_CODE = 4021;

export type LessonResetPhase = 'idle' | 'checking' | 'ready' | 'exhausted';

/**
 * Ask the backend whether this learner may still reset the lesson while a reset
 * surface is open. A failed read falls back to `ready`: the reset request itself
 * is the authoritative check and reports exhaustion with code 4021.
 */
export const useLessonResetStatus = (
  lessonId: string | undefined,
  active: boolean,
) => {
  const courseId = useEnvStore(state => state.courseId);
  const preview = useSystemStore(state => state.previewMode);
  const identity = useUserStore(
    state => state.userInfo?.user_id || state.getToken(),
  );
  const initialized = useUserStore(state => state.isInitialized);
  const resetting = useCourseStore(
    state => state.resettingLessonId === lessonId,
  );
  const scope = JSON.stringify([courseId, lessonId, identity, preview]);
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const requestVersion = useRef(0);
  const [status, setStatus] = useState<{
    scope: string;
    phase: LessonResetPhase;
  }>({ scope, phase: 'idle' });
  const phase = status.scope === scope ? status.phase : 'idle';

  const refresh = useCallback(async (): Promise<LessonResetPhase> => {
    if (!initialized || !identity || !courseId || !lessonId) return 'idle';
    const version = ++requestVersion.current;
    setStatus({ scope, phase: 'checking' });
    let next: LessonResetPhase;
    try {
      const result = await getLessonResetStatus(lessonId);
      next = result.can_reset === false ? 'exhausted' : 'ready';
    } catch {
      next = 'ready';
    }
    if (currentScope.current !== scope || version !== requestVersion.current)
      return 'idle';
    setStatus({ scope, phase: next });
    return next;
  }, [courseId, initialized, lessonId, scope, identity]);

  useEffect(() => {
    if (active && !resetting) void refresh();
    return () => {
      requestVersion.current += 1;
    };
  }, [active, refresh, resetting]);

  const setFailure = useCallback(
    (error: unknown) => {
      const code = (error as { code?: number } | null)?.code;
      if (code === LESSON_RESET_LIMIT_REACHED_CODE) {
        setStatus({ scope, phase: 'exhausted' });
      }
    },
    [scope],
  );

  return { phase, refresh, setFailure };
};

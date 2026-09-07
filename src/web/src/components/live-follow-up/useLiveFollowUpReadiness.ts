'use client';

import { useCallback, useEffect, useState } from 'react';
import { getLiveFollowUpReadiness } from '@/lib/liveVoiceFollowUp';

export type LiveReadinessState =
  | 'checking'
  | 'ready'
  | 'warming'
  | 'unavailable';

/** Probe only; never activates audio, requests permission, or mints credentials. */
export const useLiveFollowUpReadiness = (scope: string) => {
  const [enabledScope, setEnabledScope] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [snapshot, setSnapshot] = useState({
    scope,
    state: 'checking' as LiveReadinessState,
  });
  const prepare = useCallback(() => setEnabledScope(scope), [scope]);
  const refresh = useCallback(() => {
    setSnapshot({ scope, state: 'checking' });
    setEnabledScope(scope);
    setRevision(value => value + 1);
  }, [scope]);

  useEffect(() => {
    if (enabledScope !== scope) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let abort: AbortController | undefined;
    const probe = async () => {
      if (disposed || document.hidden) return;
      abort = new AbortController();
      const current = abort;
      const timeout = setTimeout(() => current.abort(), 5000);
      let delay = 30000;
      let ready = false;
      try {
        const result = await getLiveFollowUpReadiness(current.signal);
        if (disposed || current.signal.aborted) return;
        ready = result.status === 'ready';
        setSnapshot({
          scope,
          state: ready
            ? 'ready'
            : result.status === 'warming'
              ? 'warming'
              : 'unavailable',
        });
        if (Number.isFinite(result.retry_after_ms))
          delay = Math.min(30000, Math.max(1000, result.retry_after_ms!));
      } catch {
        if (!disposed && !document.hidden && abort === current)
          setSnapshot({ scope, state: 'unavailable' });
      } finally {
        clearTimeout(timeout);
        if (abort === current) {
          abort = undefined;
          if (!disposed && !document.hidden && !ready)
            timer = setTimeout(probe, delay);
        }
      }
    };
    const visibility = () => {
      clearTimeout(timer);
      abort?.abort();
      abort = undefined;
      if (!document.hidden) void probe();
    };
    document.addEventListener('visibilitychange', visibility);
    void probe();
    return () => {
      disposed = true;
      clearTimeout(timer);
      abort?.abort();
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [enabledScope, revision, scope]);

  return {
    readiness:
      snapshot.scope === scope ? snapshot.state : ('checking' as const),
    prepare,
    refresh,
  };
};

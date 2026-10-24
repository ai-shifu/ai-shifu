import { useEffect, useRef } from 'react';
import { useTracking } from '@/hooks/useTracking';
import type { LiveFollowUpSurface } from '@/lib/liveVoiceFollowUp';
import type { LiveReadinessState } from './useLiveFollowUpReadiness';

export const LIVE_READINESS_EVENT = 'learner_voice_follow_up_readiness';

/** Observe the panel, not background probes or attempted disabled actions. */
export const useLiveReadinessAnalytics = ({
  enabled,
  previewMode,
  shifuBid,
  outlineBid,
  anchorElementBid,
  surface,
  state,
}: {
  enabled: boolean;
  previewMode: boolean;
  shifuBid: string;
  outlineBid: string;
  anchorElementBid: string;
  surface: LiveFollowUpSurface;
  state: LiveReadinessState;
}) => {
  const { trackEvent } = useTracking();
  const observed = useRef<{
    scope: string;
    states: Set<LiveReadinessState>;
  } | null>(null);
  const scope = JSON.stringify([
    shifuBid,
    outlineBid,
    anchorElementBid,
    surface,
  ]);
  useEffect(() => {
    if (
      !enabled ||
      previewMode ||
      (surface !== 'read_content' && surface !== 'listen_player')
    ) {
      observed.current = null;
      return;
    }
    if (observed.current?.scope !== scope)
      observed.current = { scope, states: new Set() };
    const observe = () => {
      const current = observed.current;
      if (document.hidden || !current || current.states.has(state)) return;
      const initial = current.states.size === 0;
      current.states.add(state);
      try {
        void Promise.resolve(
          trackEvent(LIVE_READINESS_EVENT, {
            shifu_bid: shifuBid,
            outline_bid: outlineBid,
            learning_mode: surface === 'listen_player' ? 'listen' : 'read',
            surface,
            state,
            initial,
          }),
        ).catch(() => {});
      } catch {}
    };
    observe();
    document.addEventListener('visibilitychange', observe);
    return () => document.removeEventListener('visibilitychange', observe);
  }, [
    enabled,
    previewMode,
    scope,
    shifuBid,
    outlineBid,
    surface,
    state,
    trackEvent,
  ]);
};

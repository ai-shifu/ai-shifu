'use client';

import { useCallback, useEffect, useRef } from 'react';

type StopHandler = () => void;

let activeAudioId: symbol | null = null;
let activeAudioStop: StopHandler | null = null;

export interface ExclusiveAudioControls {
  requestExclusive: (stop: StopHandler) => void;
  releaseExclusive: () => void;
}

export function useExclusiveAudio(): ExclusiveAudioControls {
  const instanceIdRef = useRef<symbol>(Symbol('exclusive-audio'));

  const requestExclusive = useCallback((stop: StopHandler) => {
    if (activeAudioId && activeAudioId !== instanceIdRef.current) {
      activeAudioStop?.();
    }
    activeAudioId = instanceIdRef.current;
    activeAudioStop = stop;
  }, []);

  const releaseExclusive = useCallback(() => {
    if (activeAudioId === instanceIdRef.current) {
      activeAudioId = null;
      activeAudioStop = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      if (activeAudioId === instanceIdRef.current) {
        activeAudioId = null;
        activeAudioStop = null;
      }
    };
  }, []);

  return { requestExclusive, releaseExclusive };
}

export default useExclusiveAudio;

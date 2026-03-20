'use client';

import { useCallback, useEffect, useRef } from 'react';

type StopHandler = () => void;

let activeAudioId: symbol | null = null;
let activeAudioStop: StopHandler | null = null;
let activeAudioDebugKey: string | null = null;

const getExclusiveAudioCaller = () => {
  const stackLines = new Error().stack?.split('\n') ?? [];
  return stackLines[3]?.trim() || stackLines[2]?.trim() || 'unknown-caller';
};

const logExclusiveAudioDebug = (
  event: string,
  payload?: Record<string, unknown>,
) => {
  // if (process.env.NODE_ENV === 'production') {
  return;
  // }
  console.log(`[音频中断排查][排他音频] ${event}`, payload ?? {});
};

export interface ExclusiveAudioControls {
  requestExclusive: (stop: StopHandler) => void;
  releaseExclusive: () => void;
}

export function useExclusiveAudio(): ExclusiveAudioControls {
  const instanceIdRef = useRef<symbol>(Symbol('exclusive-audio'));
  const debugKeyRef = useRef(`audio-${Math.random().toString(36).slice(2, 8)}`);

  const requestExclusive = useCallback((stop: StopHandler) => {
    if (activeAudioId && activeAudioId !== instanceIdRef.current) {
      logExclusiveAudioDebug('检测到新音频实例抢占，将触发旧实例停止', {
        from: activeAudioDebugKey,
        to: debugKeyRef.current,
        caller: getExclusiveAudioCaller(),
      });
      activeAudioStop?.();
      logExclusiveAudioDebug('旧实例停止回调执行完成', {
        from: activeAudioDebugKey,
        to: debugKeyRef.current,
      });
    } else if (activeAudioId === instanceIdRef.current) {
      // Skip repeated self-ownership logs to avoid console flooding in listen mode.
    } else {
      logExclusiveAudioDebug('当前无活跃音频，设置排他权限', {
        owner: debugKeyRef.current,
        caller: getExclusiveAudioCaller(),
      });
    }
    activeAudioId = instanceIdRef.current;
    activeAudioStop = stop;
    activeAudioDebugKey = debugKeyRef.current;
  }, []);

  const releaseExclusive = useCallback(() => {
    if (activeAudioId === instanceIdRef.current) {
      logExclusiveAudioDebug('释放排他权限', {
        owner: debugKeyRef.current,
        caller: getExclusiveAudioCaller(),
      });
      activeAudioId = null;
      activeAudioStop = null;
      activeAudioDebugKey = null;
      return;
    }
    logExclusiveAudioDebug('跳过释放排他权限（当前实例不是持有者）', {
      owner: debugKeyRef.current,
      holder: activeAudioDebugKey,
      caller: getExclusiveAudioCaller(),
    });
  }, []);

  useEffect(() => {
    return () => {
      if (activeAudioId === instanceIdRef.current) {
        logExclusiveAudioDebug('组件卸载，清理排他权限', {
          owner: debugKeyRef.current,
        });
        activeAudioId = null;
        activeAudioStop = null;
        activeAudioDebugKey = null;
      }
    };
  }, []);

  return { requestExclusive, releaseExclusive };
}

export default useExclusiveAudio;

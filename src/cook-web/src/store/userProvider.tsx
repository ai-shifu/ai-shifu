'use client';

import { useEffect } from 'react';

import { inWechat } from '@/c-constants/uiConstants';
import { useEnvStore, useSystemStore } from '@/c-store';
import { parseUrlParams } from '@/c-utils/urlUtils';
import { useUserStore } from '@/store';

export const UserProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const initUser = useUserStore(state => state.initUser);
  const isInitialized = useUserStore(state => state.isInitialized);

  const runtimeConfigLoaded = useEnvStore(state => state.runtimeConfigLoaded);
  const enableWxcode = useEnvStore(state => state.enableWxcode);
  const wechatCode = useSystemStore(state => state.wechatCode);
  const updateWechatCode = useSystemStore(state => state.updateWechatCode);

  useEffect(() => {
    if (!runtimeConfigLoaded) {
      return;
    }

    const wxcodeEnabled =
      typeof enableWxcode === 'string' && enableWxcode.toLowerCase() === 'true';
    const onCourseRoute =
      typeof window !== 'undefined' &&
      window.location.pathname.startsWith('/c');

    if (wxcodeEnabled && onCourseRoute && inWechat()) {
      const params = parseUrlParams() as Record<string, string | undefined>;
      const codeInUrl = params.code;
      if (codeInUrl && codeInUrl !== wechatCode) {
        updateWechatCode(codeInUrl);
      }
      // Wait until the OAuth code is available so require_tmp can carry it
      if (!wechatCode && !codeInUrl) {
        return;
      }
    }

    if (!isInitialized) {
      initUser();
    }
  }, [
    runtimeConfigLoaded,
    enableWxcode,
    wechatCode,
    updateWechatCode,
    initUser,
    isInitialized,
  ]);

  return <>{children}</>;
};

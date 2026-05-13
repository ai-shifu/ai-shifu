'use client';

import { useEffect } from 'react';

import {
  inMiniProgram,
  inWechat,
  wechatLogin,
} from '@/c-constants/uiConstants';
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
  const appId = useEnvStore(state => state.appId);
  const wechatCode = useSystemStore(state => state.wechatCode);
  const updateWechatCode = useSystemStore(state => state.updateWechatCode);

  useEffect(() => {
    if (!runtimeConfigLoaded) {
      return;
    }

    const wxcodeEnabled =
      typeof enableWxcode === 'string' && enableWxcode.toLowerCase() === 'true';
    const onWxcodeProtectedRoute =
      typeof window !== 'undefined' &&
      (window.location.pathname.startsWith('/c') ||
        window.location.pathname.startsWith('/admin'));

    if (
      wxcodeEnabled &&
      onWxcodeProtectedRoute &&
      inWechat() &&
      !inMiniProgram()
    ) {
      const params = parseUrlParams() as Record<string, string | undefined>;
      const codeInUrl = params.code;

      if (codeInUrl && codeInUrl !== wechatCode) {
        updateWechatCode(codeInUrl);
      }

      if (!codeInUrl && !wechatCode) {
        if (appId) {
          wechatLogin({ appId });
          return;
        }
      }
    }

    if (!isInitialized) {
      initUser();
    }
  }, [
    runtimeConfigLoaded,
    enableWxcode,
    appId,
    wechatCode,
    updateWechatCode,
    initUser,
    isInitialized,
  ]);

  return <>{children}</>;
};

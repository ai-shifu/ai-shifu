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
    const pathname =
      typeof window !== 'undefined' ? window.location.pathname : '';
    const onCourseRoute = pathname.startsWith('/c');
    const onAdminRoute = pathname.startsWith('/admin');

    if (
      wxcodeEnabled &&
      (onCourseRoute || onAdminRoute) &&
      inWechat() &&
      !inMiniProgram()
    ) {
      const params = parseUrlParams() as Record<string, string | undefined>;
      const codeInUrl = params.code;

      if (codeInUrl && codeInUrl !== wechatCode) {
        updateWechatCode(codeInUrl);
      }

      if (!codeInUrl && !wechatCode) {
        if (onAdminRoute && appId) {
          wechatLogin({ appId });
          return;
        }

        if (onCourseRoute) {
          // `/c` keeps its existing route-local OAuth redirect flow and only
          // waits here until that path hydrates a usable wxcode.
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

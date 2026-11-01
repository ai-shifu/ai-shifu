import { useEffect, useRef, useState } from 'react';
import { updateWxcode } from '@/api/user';
import { inMiniProgram, inWechat, wechatLogin } from '@/constants/ui-constants';
import { debugWarn } from '@/lib/debug-console';
import { removeParamFromUrl } from '@/lib/url-utils';

export const WECHAT_OPENID_BINDING_TIMEOUT_MS = 10_000;
const OPENID_REBIND_SESSION_KEY = 'wechat_openid_rebind_attempted';

type BindingIdentity = {
  userId: string;
  token: string;
  code: string;
};

type BindingAttempt = BindingIdentity & {
  phase: 'pending' | 'redirecting' | 'ready';
  deadline: number;
  exchange?: Promise<string>;
  refresh?: Promise<unknown>;
};

type WechatOpenIdBindingParams = BindingIdentity & {
  initialized: boolean;
  isLoggedIn: boolean;
  userProfileLoaded: boolean;
  openId: string;
  enabled: boolean;
  appId: string;
  refreshUserInfo: () => Promise<unknown>;
  authorize?: typeof wechatLogin;
};

const sameIdentity = (left: BindingIdentity, right: BindingIdentity) =>
  left.token === right.token &&
  left.code === right.code &&
  // A retained sign-in token can precede a successful account-info response.
  (!left.userId || !right.userId || left.userId === right.userId);

/** Settle any full-page WeChat recovery before starting Profile collection. */
export const useWechatOpenIdBinding = (
  params: WechatOpenIdBindingParams,
): boolean => {
  const {
    initialized,
    isLoggedIn,
    userId,
    token,
    code,
    userProfileLoaded,
    openId,
    enabled,
    appId,
    refreshUserInfo,
    authorize = wechatLogin,
  } = params;
  const applicable =
    initialized && isLoggedIn && enabled && inWechat() && !inMiniProgram();
  const latestRef = useRef({ params, applicable });
  latestRef.current = { params, applicable };
  const attemptRef = useRef<BindingAttempt | null>(null);
  const [settledAttempt, setSettledAttempt] = useState<BindingAttempt | null>(
    null,
  );

  useEffect(() => {
    if (!applicable || !token) {
      attemptRef.current = null;
      setSettledAttempt(null);
      return;
    }
    let attempt = attemptRef.current;
    if (!attempt || !sameIdentity(attempt, { userId, token, code })) {
      attempt = {
        userId,
        token,
        code,
        phase: 'pending',
        deadline: Date.now() + WECHAT_OPENID_BINDING_TIMEOUT_MS,
      };
      attemptRef.current = attempt;
    }
    if (!attempt.userId && userId) attempt.userId = userId;
    // A replayed effect subscribes to the same single-use code exchange.
    const currentAttempt = attempt;
    let attached = true;
    const isCurrent = () =>
      attached &&
      attemptRef.current === currentAttempt &&
      latestRef.current.applicable &&
      sameIdentity(currentAttempt, latestRef.current.params);
    const isPending = () => isCurrent() && currentAttempt.phase === 'pending';
    const release = () => {
      if (!isCurrent()) return;
      currentAttempt.phase = 'ready';
      setSettledAttempt({ ...currentAttempt });
    };

    const recover = () => {
      if (!isPending()) return;
      if (latestRef.current.params.openId.trim() || !appId) {
        release();
        return;
      }
      try {
        if (sessionStorage.getItem(OPENID_REBIND_SESSION_KEY)) {
          release();
          return;
        }
        // Without this marker recovery could loop on every OAuth return.
        sessionStorage.setItem(OPENID_REBIND_SESSION_KEY, '1');
      } catch {
        release();
        return;
      }
      currentAttempt.phase = 'redirecting';
      setSettledAttempt({ ...currentAttempt });
      try {
        authorize({
          appId,
          redirectUrl: removeParamFromUrl(window.location.href, [
            'code',
            'state',
          ]),
        });
      } catch (error) {
        debugWarn(
          '[lesson-page] WeChat OpenID recovery could not navigate',
          error,
        );
        release();
      }
    };

    const timeout = window.setTimeout(
      () => {
        if (!isPending()) return;
        // Retire the attempt before releasing Profile: a late result must not
        // navigate away from the collection that is about to start.
        debugWarn('[lesson-page] WeChat OpenID preparation timed out');
        release();
      },
      Math.max(0, currentAttempt.deadline - Date.now()),
    );

    if (currentAttempt.phase !== 'pending') {
      setSettledAttempt({ ...currentAttempt });
    } else if (!userProfileLoaded) {
      // Account-info failures retain the sign-in token. Include this wait in
      // the same deadline, and never recover late after Profile is released.
    } else if (!code) {
      recover();
    } else {
      currentAttempt.exchange ??= new Promise(resolve => {
        resolve(updateWxcode({ wxcode: code }));
      });
      void currentAttempt.exchange.then(
        async exchangedOpenId => {
          if (!isPending()) return;
          if (!exchangedOpenId) {
            debugWarn('[lesson-page] WeChat OpenID binding returned no openid');
            recover();
            return;
          }
          if (
            !currentAttempt.refresh &&
            exchangedOpenId !== latestRef.current.params.openId.trim()
          ) {
            currentAttempt.refresh = new Promise(resolve => {
              resolve(refreshUserInfo());
            });
          }
          try {
            await currentAttempt.refresh;
          } catch (error) {
            if (isPending()) {
              debugWarn(
                '[lesson-page] failed to refresh WeChat account info',
                error,
              );
            }
          }
          if (isPending()) release();
        },
        error => {
          if (!isPending()) return;
          debugWarn('[lesson-page] failed to update WeChat OpenID', error);
          recover();
        },
      );
    }

    return () => {
      attached = false;
      window.clearTimeout(timeout);
    };
  }, [
    applicable,
    token,
    userId,
    code,
    userProfileLoaded,
    openId,
    appId,
    refreshUserInfo,
    authorize,
  ]);

  if (!applicable || !token) return true;
  return Boolean(
    settledAttempt?.phase === 'ready' && sameIdentity(settledAttempt, params),
  );
};

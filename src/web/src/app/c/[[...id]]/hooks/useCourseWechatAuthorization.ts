import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { inMiniProgram, inWechat, wechatLogin } from '@/constants/uiConstants';
import { debugWarn } from '@/lib/debugConsole';

type CourseWechatAuthorization = {
  ready: boolean;
  preparationAbandoned: boolean;
  authorize: typeof wechatLogin;
};

const CourseWechatAuthorizationContext =
  createContext<CourseWechatAuthorization>({
    ready: true,
    preparationAbandoned: false,
    authorize: wechatLogin,
  });

export const CourseWechatAuthorizationProvider =
  CourseWechatAuthorizationContext.Provider;
export const useCourseWechatAuthorization = () =>
  useContext(CourseWechatAuthorizationContext);

type CourseWechatAuthorizationParams = {
  runtimeConfigLoaded: boolean;
  enabled: boolean;
  appId: string;
  queryCode: string;
  wechatCode: string;
  updateWechatCode: (code: string) => void;
};

/** Own every course OAuth navigation for the lifetime of the parent layout. */
export const useCourseWechatAuthorizationState = ({
  runtimeConfigLoaded,
  enabled,
  appId,
  queryCode,
  wechatCode,
  updateWechatCode,
}: CourseWechatAuthorizationParams): CourseWechatAuthorization => {
  const applicable = enabled && inWechat() && !inMiniProgram();
  const navigationStartedRef = useRef(false);
  const preparationAbandonedRef = useRef(false);
  const attemptedAppIdRef = useRef<string | null>(null);
  const [navigationPending, setNavigationPending] = useState(false);
  const [preparationAbandoned, setPreparationAbandoned] = useState(false);
  const [failedAppId, setFailedAppId] = useState<string | null>(null);

  const authorize = useCallback<typeof wechatLogin>(options => {
    if (navigationStartedRef.current || preparationAbandonedRef.current) return;
    // Set the shared lock before assigning location. A child remount or a
    // deadline cannot cancel an already-issued full-page navigation.
    navigationStartedRef.current = true;
    setNavigationPending(true);
    try {
      wechatLogin(options);
    } catch (error) {
      navigationStartedRef.current = false;
      setNavigationPending(false);
      throw error;
    }
  }, []);

  useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (!event.persisted || !navigationStartedRef.current) return;
      // BFCache restoration proves the document left and has returned. Retire
      // that navigation and skip automatic retries and spent-code exchanges.
      preparationAbandonedRef.current = true;
      navigationStartedRef.current = false;
      setPreparationAbandoned(true);
      setNavigationPending(false);
    };
    window.addEventListener('pageshow', onPageShow);
    return () => window.removeEventListener('pageshow', onPageShow);
  }, []);

  useEffect(() => {
    if (!runtimeConfigLoaded || !applicable || !appId) return;
    if (queryCode) {
      if (queryCode !== wechatCode) updateWechatCode(queryCode);
      return;
    }
    if (attemptedAppIdRef.current === appId) return;
    attemptedAppIdRef.current = appId;
    try {
      authorize({ appId });
    } catch (error) {
      debugWarn(
        '[lesson-layout] WeChat authorization could not navigate',
        error,
      );
      setFailedAppId(appId);
    }
  }, [
    runtimeConfigLoaded,
    applicable,
    appId,
    queryCode,
    wechatCode,
    updateWechatCode,
    authorize,
  ]);

  const ready =
    !navigationPending &&
    runtimeConfigLoaded &&
    (preparationAbandoned ||
      !applicable ||
      !appId ||
      (queryCode ? queryCode === wechatCode : failedAppId === appId));

  return useMemo(
    () => ({ ready, preparationAbandoned, authorize }),
    [ready, preparationAbandoned, authorize],
  );
};

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { inMiniProgram, inWechat, wechatLogin } from '@/constants/ui-constants';
import { debugWarn } from '@/lib/debug-console';
import { useEnvStore } from '@/store/env-store';

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
  courseId: string;
  runtimeConfigLoaded: boolean;
  enabled: boolean;
  appId: string;
  queryCode: string;
  wechatCode: string;
  updateWechatCode: (code: string) => void;
};

/** Own every course OAuth navigation for the lifetime of the parent layout. */
export const useCourseWechatAuthorizationState = ({
  courseId,
  runtimeConfigLoaded,
  enabled,
  appId,
  queryCode,
  wechatCode,
  updateWechatCode,
}: CourseWechatAuthorizationParams): CourseWechatAuthorization => {
  const runtimeContext = useEnvStore(state => state.runtimeConfigContext);
  const contextMatches = runtimeContext?.courseId === courseId;
  const contextSettled = contextMatches && runtimeContext.status !== 'loading';
  const contextSucceeded = contextMatches && runtimeContext.status === 'ready';
  const currentCourseRef = useRef(courseId);
  currentCourseRef.current = courseId;
  const mountedRef = useRef(true);
  useLayoutEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
  const applicable = enabled && inWechat() && !inMiniProgram();
  const navigationStartedRef = useRef(false);
  const preparationAbandonedRef = useRef(false);
  const authorizationKey = JSON.stringify([
    courseId,
    runtimeContext?.generation,
    appId,
  ]);
  const attemptedContextRef = useRef<string | null>(null);
  const [navigationPending, setNavigationPending] = useState(false);
  const [preparationAbandoned, setPreparationAbandoned] = useState(false);
  const [failedContext, setFailedContext] = useState<string | null>(null);

  const isCurrentContext = useCallback(() => {
    const current = useEnvStore.getState();
    return (
      mountedRef.current &&
      currentCourseRef.current === courseId &&
      runtimeConfigLoaded &&
      contextSucceeded &&
      current.runtimeConfigLoaded &&
      current.runtimeConfigContext?.courseId === courseId &&
      current.runtimeConfigContext.status === 'ready' &&
      current.runtimeConfigContext.generation === runtimeContext?.generation &&
      current.appId === appId &&
      current.enableWxcode.toLowerCase() === 'true'
    );
  }, [
    courseId,
    runtimeConfigLoaded,
    contextSucceeded,
    runtimeContext?.generation,
    appId,
  ]);

  const authorize = useCallback<typeof wechatLogin>(
    options => {
      // Recheck the shared snapshot at the actual navigation boundary. A route
      // update may invalidate a callback/effect captured before React rerenders.
      if (
        !applicable ||
        !appId ||
        options.appId !== appId ||
        !isCurrentContext()
      )
        return;
      if (navigationStartedRef.current || preparationAbandonedRef.current)
        return;
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
    },
    [applicable, appId, isCurrentContext],
  );

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
    if (
      !runtimeConfigLoaded ||
      !contextSucceeded ||
      !applicable ||
      !appId ||
      !isCurrentContext()
    )
      return;
    if (queryCode) {
      if (queryCode !== wechatCode) updateWechatCode(queryCode);
      return;
    }
    if (attemptedContextRef.current === authorizationKey) return;
    attemptedContextRef.current = authorizationKey;
    try {
      authorize({ appId });
    } catch (error) {
      debugWarn(
        '[lesson-layout] WeChat authorization could not navigate',
        error,
      );
      updateWechatCode('');
      setFailedContext(authorizationKey);
    }
  }, [
    runtimeConfigLoaded,
    contextSucceeded,
    applicable,
    appId,
    authorizationKey,
    queryCode,
    wechatCode,
    updateWechatCode,
    authorize,
    isCurrentContext,
  ]);

  const ready =
    !navigationPending &&
    runtimeConfigLoaded &&
    contextSettled &&
    (preparationAbandoned ||
      !contextSucceeded ||
      !applicable ||
      !appId ||
      (queryCode
        ? queryCode === wechatCode
        : failedContext === authorizationKey && !wechatCode));

  return useMemo(
    () => ({ ready, preparationAbandoned, authorize }),
    [ready, preparationAbandoned, authorize],
  );
};

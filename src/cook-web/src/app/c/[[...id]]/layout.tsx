'use client';

import { useEffect, useRef, useState } from 'react';
import {
  parseUrlParams,
  replaceCurrentUrlWithCanonicalCourseRoute,
} from '@/c-utils/urlUtils';
// import routes from './Router/index';
// import { useRoutes } from 'react-router-dom';
// import { ConfigProvider } from 'antd';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useTranslation } from 'react-i18next';
import { debugError, debugInfo } from '@/c-utils/debugConsole';

import { useShallow } from 'zustand/react/shallow';
import { useParams } from 'next/navigation';

import {
  inWechat,
  inMiniProgram,
  wechatLogin,
} from '@/c-constants/uiConstants';
import { getCourseInfo } from '@/c-api/course';
import { tracking } from '@/c-common/tools/tracking';
import { useTracking } from '@/c-common/hooks/useTracking';
import {
  EnvStoreState,
  SystemStoreState,
  CourseStoreState,
} from '@/c-types/store';

import { useEnvStore, useCourseStore } from '@/c-store';
import { UserProvider } from '@/store/userProvider';
import { useUserStore } from '@/store/useUserStore';
import {
  readLearningModeFromStorage,
  writeLearningModeToStorage,
} from './Components/learningModeStorage';
import { resolveCourseLearningMode } from './Components/learningModePreference';
import {
  normalizeLegacyListenModeInUrl,
  parseBooleanQueryParam,
  parseLearningModeQueryParam,
  setLearningModeInUrl,
} from './Components/learningModeUrl';

const CLASSROOM_ACCESS_DENIAL_STATUSES = new Set([401, 403, 404]);
const classroomAccessRequestByCourseId = new Map<
  string,
  Promise<boolean | null>
>();

type ResolvedCourseIdentity = {
  requestedIdentifier: string;
  bid: string;
  slug: string;
  previewMode: boolean;
};

type CourseBootstrapFailure = {
  requestedIdentifier: string;
  previewMode: boolean;
};

const isDefinitiveClassroomAccessDenial = (error: unknown) => {
  const fetchError = error as {
    code?: number | string;
    isCourseNotFound?: boolean;
    status?: number | string;
  };

  if (fetchError?.isCourseNotFound) {
    return true;
  }

  const status = Number(fetchError?.status ?? fetchError?.code);
  return CLASSROOM_ACCESS_DENIAL_STATUSES.has(status);
};

const getClassroomAccessForCourse = (courseId: string) => {
  const existingRequest = classroomAccessRequestByCourseId.get(courseId);
  if (existingRequest) {
    return existingRequest;
  }

  const accessRequest = getCourseInfo(courseId, true, {
    skipErrorToast: true,
    trackErrors: false,
  })
    .then(() => true)
    .catch(error => (isDefinitiveClassroomAccessDenial(error) ? false : null))
    .finally(() => {
      classroomAccessRequestByCourseId.delete(courseId);
    });

  classroomAccessRequestByCourseId.set(courseId, accessRequest);
  return accessRequest;
};

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const trackedLearningModeStorageRef = useRef<string>('');
  const { i18n, t } = useTranslation();
  const { trackEvent } = useTracking();
  const routeParams = useParams<{ id?: string[] }>();

  const [checkWxcode, setCheckWxcode] = useState<boolean>(false);
  const envDataInitialized = useEnvStore(
    (state: EnvStoreState) => state.runtimeConfigLoaded,
  );

  const {
    updateChannel,
    channel,
    wechatCode,
    updateWechatCode,
    setShowVip,
    updateLanguage,
    updatePreviewMode,
    updateSkip,
    updateShowLearningModeToggle,
    canUseClassroomMode,
    updateCanUseClassroomMode,
    learningMode,
    updateLearningMode,
  } = useSystemStore() as SystemStoreState;

  // Use the original browser language without conversion
  const browserLanguage = navigator.language || navigator.languages?.[0];

  const [language] = useState(browserLanguage);
  const [classroomAccessCourseId, setClassroomAccessCourseId] = useState<
    string | null
  >(null);

  const courseId = useEnvStore((state: EnvStoreState) => state.courseId);
  const updateCourseIdentity = useEnvStore(
    (state: EnvStoreState) => state.updateCourseIdentity,
  );
  const enableWxcode = useEnvStore(
    (state: EnvStoreState) => state.enableWxcode,
  );

  const {
    courseTtsEnabled,
    updateCourseName,
    updateCourseAvatar,
    updateCourseTtsEnabled,
  } = useCourseStore(
    useShallow((state: CourseStoreState) => ({
      courseTtsEnabled: state.courseTtsEnabled,
      updateCourseName: state.updateCourseName,
      updateCourseAvatar: state.updateCourseAvatar,
      updateCourseTtsEnabled: state.updateCourseTtsEnabled,
    })),
  );

  const { userInfo, initUser, isInitialized, isLoggedIn } = useUserStore();

  useEffect(() => {
    if (!envDataInitialized) return;
    if (userInfo?.language) {
      updateLanguage(userInfo.language);
    } else {
      updateLanguage(browserLanguage);
    }
  }, [browserLanguage, updateLanguage, envDataInitialized, userInfo]);

  // const [loading, setLoading] = useState<boolean>(true);
  const params = parseUrlParams() as Record<string, string>;
  const routeCourseIdentifier = Array.isArray(routeParams?.id)
    ? routeParams.id[0]
    : '';
  const queryCourseIdentifier = params.courseId || '';
  const courseIdentifier =
    routeCourseIdentifier || queryCourseIdentifier || courseId;
  const storageCourseId = courseId;
  const outlineBid = params.lessonid || '';
  const currChannel = params.channel || '';
  const isPreviewMode = parseBooleanQueryParam(params.preview) ?? false;
  const isSkipMode = parseBooleanQueryParam(params.skip) ?? false;
  const [resolvedCourseIdentity, setResolvedCourseIdentity] =
    useState<ResolvedCourseIdentity | null>(null);
  const [courseBootstrapFailure, setCourseBootstrapFailure] =
    useState<CourseBootstrapFailure | null>(null);
  const [courseBootstrapAttempt, setCourseBootstrapAttempt] = useState(0);
  const courseBootstrapReady = Boolean(
    envDataInitialized &&
    resolvedCourseIdentity &&
    resolvedCourseIdentity.previewMode === isPreviewMode &&
    resolvedCourseIdentity.bid === courseId &&
    (!courseIdentifier ||
      courseIdentifier === resolvedCourseIdentity.requestedIdentifier ||
      courseIdentifier === resolvedCourseIdentity.bid ||
      courseIdentifier === resolvedCourseIdentity.slug),
  );
  const courseBootstrapFailed = Boolean(
    courseBootstrapFailure &&
    courseBootstrapFailure.requestedIdentifier === courseIdentifier &&
    courseBootstrapFailure.previewMode === isPreviewMode,
  );
  const listenModeParam = parseBooleanQueryParam(params.listen);
  const urlModeParam = parseLearningModeQueryParam(params.mode);
  const hasListenModeOverride = listenModeParam !== null;
  const hasClassroomModeOverride = urlModeParam === 'classroom';
  const canUseClassroomModeForCourse =
    classroomAccessCourseId === storageCourseId ? canUseClassroomMode : null;
  const isCourseListenModeAvailable = courseTtsEnabled === true;
  const hasListenModeUrlOverride = urlModeParam === 'listen';
  const hasClassroomModeUrlOverride = urlModeParam === 'classroom';
  const showLearningModeToggle =
    courseTtsEnabled === null
      ? listenModeParam === true ||
        hasListenModeUrlOverride ||
        hasClassroomModeUrlOverride ||
        canUseClassroomModeForCourse === true
      : isCourseListenModeAvailable ||
        hasListenModeUrlOverride ||
        hasClassroomModeUrlOverride ||
        canUseClassroomModeForCourse === true;

  if (channel !== currChannel) {
    updateChannel(currChannel);
  }

  useEffect(() => {
    if (!envDataInitialized) return;
    const wxcodeEnabled =
      typeof enableWxcode === 'string' && enableWxcode.toLowerCase() === 'true';
    if (!wxcodeEnabled || !inWechat() || inMiniProgram()) {
      setCheckWxcode(true);
      return;
    }

    const { appId } = useEnvStore.getState() as EnvStoreState;
    const currCode = params.code;

    if (!appId) {
      console.warn('WeChat appId missing, skip OAuth redirect');
      setCheckWxcode(true);
      return;
    }

    if (!currCode) {
      wechatLogin({
        appId,
      });
      return;
    }

    if (currCode !== wechatCode) {
      updateWechatCode(currCode);
    }
    setCheckWxcode(true);
  }, [
    params.code,
    updateWechatCode,
    wechatCode,
    envDataInitialized,
    enableWxcode,
  ]);

  useEffect(() => {
    updatePreviewMode(isPreviewMode);
    updateSkip(isSkipMode);
    updateShowLearningModeToggle(showLearningModeToggle);
  }, [
    isPreviewMode,
    isSkipMode,
    showLearningModeToggle,
    updatePreviewMode,
    updateSkip,
    updateShowLearningModeToggle,
  ]);

  useEffect(() => {
    normalizeLegacyListenModeInUrl({
      listenModeParam,
      urlModeParam,
    });
  }, [listenModeParam, urlModeParam]);

  useEffect(() => {
    if (!courseBootstrapReady || !storageCourseId) {
      return;
    }

    if (isPreviewMode) {
      setClassroomAccessCourseId(storageCourseId);
      updateCanUseClassroomMode(true);
      return;
    }

    if (!isInitialized) {
      setClassroomAccessCourseId(storageCourseId);
      updateCanUseClassroomMode(null);
      return;
    }

    if (!isLoggedIn) {
      setClassroomAccessCourseId(storageCourseId);
      updateCanUseClassroomMode(false);
      return;
    }

    let canceled = false;
    setClassroomAccessCourseId(storageCourseId);
    updateCanUseClassroomMode(null);

    getClassroomAccessForCourse(storageCourseId)
      .then(canUseClassroom => {
        if (!canceled) {
          setClassroomAccessCourseId(storageCourseId);
          updateCanUseClassroomMode(canUseClassroom);
        }
      })
      .catch(() => {
        if (!canceled) {
          setClassroomAccessCourseId(storageCourseId);
          updateCanUseClassroomMode(null);
        }
      });

    return () => {
      canceled = true;
    };
  }, [
    courseBootstrapReady,
    isInitialized,
    isLoggedIn,
    isPreviewMode,
    storageCourseId,
    updateCanUseClassroomMode,
  ]);

  useEffect(() => {
    if (!courseBootstrapReady || !hasClassroomModeOverride) {
      return;
    }

    if (canUseClassroomModeForCourse === false) {
      setLearningModeInUrl('read');
      updateLearningMode('read');
    }
  }, [
    canUseClassroomModeForCourse,
    courseBootstrapReady,
    hasClassroomModeOverride,
    updateLearningMode,
  ]);

  useEffect(() => {
    if (!courseBootstrapReady || !storageCourseId) {
      return;
    }

    const trackingKey = [
      storageCourseId,
      hasListenModeOverride || urlModeParam ? 'override' : 'default',
      urlModeParam ||
        (listenModeParam === null
          ? 'none'
          : listenModeParam
            ? 'listen'
            : 'read'),
    ].join(':');

    if (trackedLearningModeStorageRef.current === trackingKey) {
      return;
    }

    trackedLearningModeStorageRef.current = trackingKey;
    const storedLearningMode = readLearningModeFromStorage(storageCourseId);

    if (storedLearningMode === null) {
      return;
    }
    void trackEvent('learner_last_learning_mode', {
      shifu_bid: storageCourseId,
      outline_bid: outlineBid,
      learning_mode: storedLearningMode,
    });
  }, [
    hasListenModeOverride,
    courseBootstrapReady,
    listenModeParam,
    outlineBid,
    storageCourseId,
    trackEvent,
    urlModeParam,
  ]);

  useEffect(() => {
    if (!courseBootstrapReady || !storageCourseId) {
      return;
    }
    const storedLearningMode = readLearningModeFromStorage(storageCourseId);
    const nextLearningMode = resolveCourseLearningMode({
      courseTtsEnabled,
      canUseClassroomMode: canUseClassroomModeForCourse,
      hasListenModeOverride,
      listenModeParam,
      urlModeParam,
      storedLearningMode,
    });
    const currentLearningMode = useSystemStore.getState().learningMode;

    if (currentLearningMode === nextLearningMode) {
      return;
    }

    updateLearningMode(nextLearningMode);
  }, [
    courseTtsEnabled,
    canUseClassroomModeForCourse,
    courseBootstrapReady,
    hasListenModeOverride,
    listenModeParam,
    storageCourseId,
    updateLearningMode,
    urlModeParam,
  ]);

  useEffect(() => {
    if (!courseBootstrapReady || !storageCourseId) {
      return;
    }

    const storedLearningMode = readLearningModeFromStorage(storageCourseId);
    const hasPendingClassroomResolution =
      canUseClassroomModeForCourse === null &&
      learningMode === 'read' &&
      (urlModeParam === 'classroom' ||
        (!urlModeParam && storedLearningMode === 'classroom'));

    if (hasPendingClassroomResolution) {
      return;
    }

    if (storedLearningMode === learningMode) {
      return;
    }

    if (
      !urlModeParam &&
      !hasListenModeOverride &&
      storedLearningMode === null
    ) {
      return;
    }

    // Keep the course-scoped preference synced after auto resolution or manual toggles.
    writeLearningModeToStorage(storageCourseId, learningMode);
  }, [
    canUseClassroomModeForCourse,
    courseBootstrapReady,
    hasListenModeOverride,
    learningMode,
    storageCourseId,
    urlModeParam,
  ]);

  useEffect(() => {
    if (!envDataInitialized || !courseIdentifier) {
      setResolvedCourseIdentity(null);
      setCourseBootstrapFailure(null);
      return;
    }

    const matchesResolvedIdentity = Boolean(
      resolvedCourseIdentity &&
      resolvedCourseIdentity.previewMode === isPreviewMode &&
      (courseIdentifier === resolvedCourseIdentity.requestedIdentifier ||
        courseIdentifier === resolvedCourseIdentity.bid ||
        courseIdentifier === resolvedCourseIdentity.slug),
    );
    if (matchesResolvedIdentity) {
      return;
    }

    let canceled = false;
    setCourseBootstrapFailure(null);
    debugInfo('[course-info] request start', {
      courseIdentifier,
      previewMode: isPreviewMode,
      path:
        typeof window !== 'undefined'
          ? `${window.location.pathname}${window.location.search}`
          : '',
    });

    void getCourseInfo(courseIdentifier, isPreviewMode)
      .then(resp => {
        if (canceled) {
          return;
        }

        const canonicalBid = resp.course_id?.trim();
        if (!canonicalBid) {
          throw new Error('Course info response is missing canonical bid');
        }

        debugInfo('[course-info] request success', {
          courseIdentifier,
          canonicalBid,
          slug: resp.course_slug,
          previewMode: isPreviewMode,
          courseName: resp.course_name,
          coursePrice: resp.course_price,
          ttsEnabled: resp.course_tts_enabled,
        });
        void updateCourseIdentity({
          courseId: canonicalBid,
          courseSlug: resp.course_slug || '',
          courseCanonicalUrl: resp.course_canonical_url || '',
        });
        setShowVip(resp.course_price > 0);
        updateCourseName(resp.course_name);
        updateCourseAvatar(resp.course_avatar);
        updateCourseTtsEnabled(resp.course_tts_enabled ?? null);

        if (
          routeCourseIdentifier &&
          resp.course_slug &&
          routeCourseIdentifier !== resp.course_slug
        ) {
          replaceCurrentUrlWithCanonicalCourseRoute(resp.course_canonical_url);
        }

        const titleSuffix = t('common.core.brandName');
        document.title = `${resp.course_name} - ${titleSuffix}`;
        const metaDescription = document.querySelector(
          'meta[name="description"]',
        );
        if (metaDescription) {
          metaDescription.setAttribute('content', resp.course_desc);
        } else {
          const newMetaDescription = document.createElement('meta');
          newMetaDescription.setAttribute('name', 'description');
          newMetaDescription.setAttribute('content', resp.course_desc);
          document.head.appendChild(newMetaDescription);
        }
        const metaKeywords = document.querySelector('meta[name="keywords"]');
        if (metaKeywords) {
          metaKeywords.setAttribute('content', resp.course_keywords);
        } else {
          const newMetaKeywords = document.createElement('meta');
          newMetaKeywords.setAttribute('name', 'keywords');
          newMetaKeywords.setAttribute('content', resp.course_keywords);
          document.head.appendChild(newMetaKeywords);
        }
        setResolvedCourseIdentity({
          requestedIdentifier: courseIdentifier,
          bid: canonicalBid,
          slug: resp.course_slug || '',
          previewMode: isPreviewMode,
        });
      })
      .catch(error => {
        if (canceled) {
          return;
        }
        const isCourseNotFound = Boolean(
          (error as { isCourseNotFound?: boolean })?.isCourseNotFound,
        );
        debugError('[course-info] request failed', {
          courseIdentifier,
          previewMode: isPreviewMode,
          isCourseNotFound,
          errorMessage: error instanceof Error ? error.message : String(error),
          businessCode: (error as { code?: number | string })?.code ?? '',
          httpStatus: (error as { status?: number | string })?.status ?? '',
        });
        if (isCourseNotFound) {
          tracking('learner_course_404_redirect', {
            shifu_bid: courseIdentifier,
            preview_mode: isPreviewMode,
            reason: 'course_not_found',
            path: window.location.pathname,
            ua: typeof navigator !== 'undefined' ? navigator.userAgent : '',
            is_wechat:
              typeof navigator !== 'undefined' ? Boolean(inWechat()) : false,
            has_token: Boolean(useUserStore.getState().getToken()),
          });
          window.location.href = '/404';
          return;
        }

        tracking('learner_course_info_non_404_error', {
          shifu_bid: courseIdentifier,
          preview_mode: isPreviewMode,
          reason: 'transient_or_unknown_error',
          path: window.location.pathname,
          error_code:
            (error as { code?: number | string })?.code?.toString?.() || '',
          http_status:
            (error as { status?: number | string })?.status?.toString?.() || '',
          error_type:
            (error as { status?: number | string })?.status ||
            (error as { code?: number | string })?.code
              ? 'http_error'
              : 'unknown_error',
          is_wechat:
            typeof navigator !== 'undefined' ? Boolean(inWechat()) : false,
          has_token: Boolean(useUserStore.getState().getToken()),
        });
        console.warn('Skip 404 redirect for non-notfound course info error', {
          courseIdentifier,
          error,
        });
        setCourseBootstrapFailure({
          requestedIdentifier: courseIdentifier,
          previewMode: isPreviewMode,
        });
      });

    return () => {
      canceled = true;
    };
  }, [
    courseBootstrapAttempt,
    courseIdentifier,
    envDataInitialized,
    isPreviewMode,
    resolvedCourseIdentity,
    routeCourseIdentifier,
    setShowVip,
    t,
    updateCanUseClassroomMode,
    updateCourseAvatar,
    updateCourseIdentity,
    updateCourseName,
    updateCourseTtsEnabled,
  ]);

  const userLanguage = userInfo?.language;

  useEffect(() => {
    if (!envDataInitialized) {
      return;
    }

    // FIX: if userLanguage is set, use userLanguage
    if (userLanguage) {
      i18n.changeLanguage(userLanguage);
      return;
    }

    i18n.changeLanguage(language);
    updateLanguage(language);
  }, [envDataInitialized, i18n, language, updateLanguage, userLanguage]);

  useEffect(() => {
    if (!envDataInitialized) return;
    if (!checkWxcode) return;
    initUser();
  }, [envDataInitialized, checkWxcode, initUser]);

  return (
    <UserProvider>
      {courseBootstrapReady ? (
        children
      ) : courseBootstrapFailed ? (
        <main className='flex min-h-dvh items-center justify-center px-6 text-center'>
          <div className='flex max-w-sm flex-col items-center gap-4'>
            <p className='text-sm text-muted-foreground'>
              {t('common.core.requestFailed')}
            </p>
            <button
              type='button'
              className='rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground'
              onClick={() => {
                setCourseBootstrapFailure(null);
                setResolvedCourseIdentity(null);
                setCourseBootstrapAttempt(attempt => attempt + 1);
              }}
            >
              {t('common.core.retry')}
            </button>
          </div>
        </main>
      ) : null}
    </UserProvider>
  );
}

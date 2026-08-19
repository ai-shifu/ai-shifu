'use client';

import { useEffect, useRef, useState } from 'react';
// import routes from './Router/index';
// import { useRoutes } from 'react-router-dom';
// import { ConfigProvider } from 'antd';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useTranslation } from 'react-i18next';
import { debugError, debugInfo, debugWarn } from '@/c-utils/debugConsole';

import { useShallow } from 'zustand/react/shallow';
import { useParams, useSearchParams } from 'next/navigation';

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
  const searchParams = useSearchParams();

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
    previewMode,
    skip,
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
  const updateCourseId = useEnvStore(
    (state: EnvStoreState) => state.updateCourseId,
  );
  const enableWxcode = useEnvStore(
    (state: EnvStoreState) => state.enableWxcode,
  );

  const {
    courseTtsEnabled,
    courseDefaultListenModeEnabled,
    updateCourseName,
    updateCourseAvatar,
    updateCourseTtsEnabled,
    updateCourseDefaultListenModeEnabled,
  } = useCourseStore(
    useShallow((state: CourseStoreState) => ({
      courseTtsEnabled: state.courseTtsEnabled,
      courseDefaultListenModeEnabled: state.courseDefaultListenModeEnabled,
      updateCourseName: state.updateCourseName,
      updateCourseAvatar: state.updateCourseAvatar,
      updateCourseTtsEnabled: state.updateCourseTtsEnabled,
      updateCourseDefaultListenModeEnabled:
        state.updateCourseDefaultListenModeEnabled,
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
  const queryCode = searchParams?.get('code') || '';
  const queryCourseId = searchParams?.get('courseId') || '';
  const queryLessonId = searchParams?.get('lessonid') || '';
  const queryChannel = searchParams?.get('channel') || '';
  const queryPreview = searchParams?.get('preview') || '';
  const querySkip = searchParams?.get('skip') || '';
  const queryListen = searchParams?.get('listen') || '';
  const queryMode = searchParams?.get('mode') || '';
  const routeCourseId = Array.isArray(routeParams?.id) ? routeParams.id[0] : '';
  const storageCourseId = routeCourseId || queryCourseId || courseId;
  const outlineBid = queryLessonId;
  const currChannel = queryChannel;
  const isPreviewMode = parseBooleanQueryParam(queryPreview) ?? false;
  const isSkipMode = parseBooleanQueryParam(querySkip) ?? false;
  const listenModeParam = parseBooleanQueryParam(queryListen);
  const urlModeParam = parseLearningModeQueryParam(queryMode);
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

  const queryStateReady =
    channel === currChannel &&
    previewMode === isPreviewMode &&
    skip === isSkipMode;

  useEffect(() => {
    if (channel !== currChannel) {
      updateChannel(currChannel);
    }

    if (previewMode !== isPreviewMode) {
      updatePreviewMode(isPreviewMode);
    }

    if (skip !== isSkipMode) {
      updateSkip(isSkipMode);
    }
  }, [
    channel,
    currChannel,
    isPreviewMode,
    isSkipMode,
    previewMode,
    skip,
    updateChannel,
    updatePreviewMode,
    updateSkip,
  ]);

  useEffect(() => {
    if (!envDataInitialized) return;
    const wxcodeEnabled =
      typeof enableWxcode === 'string' && enableWxcode.toLowerCase() === 'true';
    if (!wxcodeEnabled || !inWechat() || inMiniProgram()) {
      setCheckWxcode(true);
      return;
    }

    const { appId } = useEnvStore.getState() as EnvStoreState;
    const currCode = queryCode;

    if (!appId) {
      debugWarn('[lesson-layout] WeChat appId missing, skip OAuth redirect');
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
    queryCode,
    updateWechatCode,
    wechatCode,
    envDataInitialized,
    enableWxcode,
  ]);

  useEffect(() => {
    const fetchCourseInfo = async () => {
      if (!envDataInitialized) return;
      if (queryCourseId) {
        await updateCourseId(queryCourseId);
      }
    };
    fetchCourseInfo();
  }, [envDataInitialized, updateCourseId, courseId, queryCourseId]);

  useEffect(() => {
    updateShowLearningModeToggle(showLearningModeToggle);
  }, [showLearningModeToggle, updateShowLearningModeToggle]);

  useEffect(() => {
    normalizeLegacyListenModeInUrl({
      listenModeParam,
      urlModeParam,
    });
  }, [listenModeParam, urlModeParam]);

  useEffect(() => {
    if (
      classroomAccessCourseId !== storageCourseId &&
      canUseClassroomMode !== null
    ) {
      updateCanUseClassroomMode(null);
    }
  }, [
    canUseClassroomMode,
    classroomAccessCourseId,
    storageCourseId,
    updateCanUseClassroomMode,
  ]);

  useEffect(() => {
    if (!envDataInitialized || !storageCourseId) {
      setClassroomAccessCourseId(null);
      updateCanUseClassroomMode(null);
      return;
    }

    if (isPreviewMode) {
      setClassroomAccessCourseId(null);
      updateCanUseClassroomMode(null);
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
    envDataInitialized,
    isInitialized,
    isLoggedIn,
    isPreviewMode,
    storageCourseId,
    updateCanUseClassroomMode,
  ]);

  useEffect(() => {
    if (!hasClassroomModeOverride) {
      return;
    }

    if (canUseClassroomModeForCourse === false) {
      setLearningModeInUrl('read');
      updateLearningMode('read');
    }
  }, [
    canUseClassroomModeForCourse,
    hasClassroomModeOverride,
    updateLearningMode,
  ]);

  useEffect(() => {
    if (!storageCourseId) {
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
    listenModeParam,
    outlineBid,
    storageCourseId,
    trackEvent,
    urlModeParam,
  ]);

  useEffect(() => {
    const storedLearningMode = readLearningModeFromStorage(storageCourseId);
    const nextLearningMode = resolveCourseLearningMode({
      courseTtsEnabled,
      courseDefaultListenModeEnabled,
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
    courseDefaultListenModeEnabled,
    canUseClassroomModeForCourse,
    hasListenModeOverride,
    listenModeParam,
    storageCourseId,
    updateLearningMode,
    urlModeParam,
  ]);

  useEffect(() => {
    if (!storageCourseId) {
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
    hasListenModeOverride,
    learningMode,
    storageCourseId,
    urlModeParam,
  ]);

  useEffect(() => {
    let canceled = false;

    const fetchCourseInfo = async () => {
      if (!envDataInitialized) return;
      if (courseId) {
        debugInfo('[course-info] request start', {
          courseId,
          previewMode: isPreviewMode,
          path:
            typeof window !== 'undefined'
              ? `${window.location.pathname}${window.location.search}`
              : '',
        });
        updateCourseTtsEnabled(null);
        updateCourseDefaultListenModeEnabled(null);
        try {
          const resp = await getCourseInfo(courseId, isPreviewMode);
          if (canceled) {
            return;
          }
          debugInfo('[course-info] request success', {
            courseId,
            previewMode: isPreviewMode,
            courseName: resp.course_name,
            coursePrice: resp.course_price,
            ttsEnabled: resp.course_tts_enabled,
            defaultListenModeEnabled: resp.default_listen_mode_enabled,
          });
          setShowVip(resp.course_price > 0);
          updateCourseName(resp.course_name);
          updateCourseAvatar(resp.course_avatar);
          updateCourseTtsEnabled(resp.course_tts_enabled ?? null);
          updateCourseDefaultListenModeEnabled(
            resp.default_listen_mode_enabled ?? null,
          );
          if (isPreviewMode) {
            setClassroomAccessCourseId(courseId);
            updateCanUseClassroomMode(true);
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
        } catch (error) {
          const isCourseNotFound = Boolean(
            (error as { isCourseNotFound?: boolean })?.isCourseNotFound,
          );
          if (canceled) {
            return;
          }
          debugError('[course-info] request failed', {
            courseId,
            previewMode: isPreviewMode,
            isCourseNotFound,
            errorMessage:
              error instanceof Error ? error.message : String(error),
            businessCode: (error as { code?: number | string })?.code ?? '',
            httpStatus: (error as { status?: number | string })?.status ?? '',
          });
          if (isCourseNotFound) {
            tracking('learner_course_404_redirect', {
              shifu_bid: courseId,
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

          // Keep users on page for transient failures instead of forcing 404.
          tracking('learner_course_info_non_404_error', {
            shifu_bid: courseId,
            preview_mode: isPreviewMode,
            reason: 'transient_or_unknown_error',
            path: window.location.pathname,
            error_code:
              (error as { code?: number | string })?.code?.toString?.() || '',
            http_status:
              (error as { status?: number | string })?.status?.toString?.() ||
              '',
            error_type:
              (error as { status?: number | string })?.status ||
              (error as { code?: number | string })?.code
                ? 'http_error'
                : 'unknown_error',
            is_wechat:
              typeof navigator !== 'undefined' ? Boolean(inWechat()) : false,
            has_token: Boolean(useUserStore.getState().getToken()),
          });
          debugWarn('[course-info] skip 404 redirect for non-notfound error', {
            courseId,
            error,
          });
          // TODO(lesson-mobile-404): sequence OAuth/checkWxcode/user init and course-info
          // requests to eliminate race windows on weak mobile networks.
        }
      }
    };
    fetchCourseInfo();
    return () => {
      canceled = true;
    };
  }, [
    courseId,
    envDataInitialized,
    setShowVip,
    t,
    updateCourseName,
    updateCourseAvatar,
    updateCourseTtsEnabled,
    updateCourseDefaultListenModeEnabled,
    updateCanUseClassroomMode,
    isPreviewMode,
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

  if (!queryStateReady) {
    return null;
  }

  return <UserProvider>{children}</UserProvider>;
}

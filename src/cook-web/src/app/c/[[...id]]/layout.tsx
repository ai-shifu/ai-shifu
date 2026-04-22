'use client';

import { useEffect, useState } from 'react';
import { parseUrlParams } from '@/c-utils/urlUtils';
// import routes from './Router/index';
// import { useRoutes } from 'react-router-dom';
// import { ConfigProvider } from 'antd';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useTranslation } from 'react-i18next';
import type { LearningMode } from './Components/learningModeOptions';

import { useShallow } from 'zustand/react/shallow';
import { useParams } from 'next/navigation';

import {
  inWechat,
  inMiniProgram,
  wechatLogin,
} from '@/c-constants/uiConstants';
import { getCourseInfo } from '@/c-api/course';
import { tracking } from '@/c-common/tools/tracking';
import {
  EnvStoreState,
  SystemStoreState,
  CourseStoreState,
} from '@/c-types/store';

import { useEnvStore, useCourseStore } from '@/c-store';
import { UserProvider, useUserStore } from '@/store';
import {
  readLearningModeFromStorage,
  writeLearningModeToStorage,
} from './Components/learningModeStorage';

const parseBooleanQueryParam = (value?: string) => {
  if (typeof value !== 'string') {
    return null;
  }

  return value.trim().toLowerCase() === 'true';
};

const resolveLearningMode = ({
  courseTtsEnabled,
  hasListenModeOverride,
  listenModeParam,
  storedLearningMode,
}: {
  courseTtsEnabled: boolean | null;
  hasListenModeOverride: boolean;
  listenModeParam: boolean | null;
  storedLearningMode: LearningMode | null;
}): LearningMode => {
  if (hasListenModeOverride) {
    if (courseTtsEnabled === null) {
      return listenModeParam === true ? 'listen' : 'read';
    }

    return listenModeParam === true && courseTtsEnabled === true
      ? 'listen'
      : 'read';
  }

  if (storedLearningMode === 'listen' && courseTtsEnabled !== false) {
    return 'listen';
  }

  return 'read';
};

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { i18n, t } = useTranslation();
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
    previewMode,
    skip,
    updatePreviewMode,
    updateSkip,
    updateShowLearningModeToggle,
    learningMode,
    updateLearningMode,
  } = useSystemStore() as SystemStoreState;

  // Use the original browser language without conversion
  const browserLanguage = navigator.language || navigator.languages?.[0];

  const [language] = useState(browserLanguage);

  const courseId = useEnvStore((state: EnvStoreState) => state.courseId);
  const updateCourseId = useEnvStore(
    (state: EnvStoreState) => state.updateCourseId,
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

  const { userInfo, initUser } = useUserStore();

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
  const routeCourseId = Array.isArray(routeParams?.id) ? routeParams.id[0] : '';
  const storageCourseId = routeCourseId || params.courseId || courseId;
  const currChannel = params.channel || '';
  const isPreviewMode = parseBooleanQueryParam(params.preview) ?? false;
  const isSkipMode = parseBooleanQueryParam(params.skip) ?? false;
  const listenModeParam = parseBooleanQueryParam(params.listen);
  const hasListenModeOverride = listenModeParam !== null;
  const isCourseListenModeAvailable = courseTtsEnabled === true;
  const showLearningModeToggle =
    courseTtsEnabled === null
      ? listenModeParam === true
      : isCourseListenModeAvailable;

  if (channel !== currChannel) {
    updateChannel(currChannel);
  }

  // Apply preview/skip flags eagerly so child components (and their effects) see
  // the correct mode on the first render.
  if (previewMode !== isPreviewMode) {
    updatePreviewMode(isPreviewMode);
  }

  if (skip !== isSkipMode) {
    updateSkip(isSkipMode);
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
    const fetchCourseInfo = async () => {
      if (!envDataInitialized) return;
      if (params.courseId) {
        await updateCourseId(params.courseId);
      }
    };
    fetchCourseInfo();
  }, [envDataInitialized, updateCourseId, courseId, params.courseId]);

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
    const storedLearningMode = readLearningModeFromStorage(storageCourseId);
    const nextLearningMode = resolveLearningMode({
      courseTtsEnabled,
      hasListenModeOverride,
      listenModeParam,
      storedLearningMode,
    });
    const currentLearningMode = useSystemStore.getState().learningMode;

    if (currentLearningMode === nextLearningMode) {
      return;
    }

    // Sync course preference or URL override into the global learning mode state.
    updateLearningMode(nextLearningMode);
  }, [
    courseTtsEnabled,
    hasListenModeOverride,
    listenModeParam,
    storageCourseId,
    updateLearningMode,
  ]);

  useEffect(() => {
    if (!storageCourseId || hasListenModeOverride) {
      return;
    }

    const storedLearningMode = readLearningModeFromStorage(storageCourseId);

    if (storedLearningMode === learningMode) {
      return;
    }

    if (storedLearningMode === null && learningMode === 'read') {
      return;
    }

    // Keep the course-scoped preference synced after user toggles mode.
    writeLearningModeToStorage(storageCourseId, learningMode);
  }, [hasListenModeOverride, learningMode, storageCourseId]);

  useEffect(() => {
    const fetchCourseInfo = async () => {
      if (!envDataInitialized) return;
      if (courseId) {
        try {
          const resp = await getCourseInfo(courseId, isPreviewMode);
          setShowVip(resp.course_price > 0);
          updateCourseName(resp.course_name);
          updateCourseAvatar(resp.course_avatar);
          updateCourseTtsEnabled(resp.course_tts_enabled ?? null);
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
          console.warn('Skip 404 redirect for non-notfound course info error', {
            courseId,
            error,
          });
          // TODO(lesson-mobile-404): sequence OAuth/checkWxcode/user init and course-info
          // requests to eliminate race windows on weak mobile networks.
        }
      }
    };
    fetchCourseInfo();
  }, [
    courseId,
    envDataInitialized,
    setShowVip,
    t,
    updateCourseName,
    updateCourseAvatar,
    updateCourseTtsEnabled,
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

  return <UserProvider>{children}</UserProvider>;
}

'use client';

import { useEffect, useState } from 'react';
import { parseUrlParams } from '@/c-utils/urlUtils';
// import routes from './Router/index';
// import { useRoutes } from 'react-router-dom';
// import { ConfigProvider } from 'antd';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useTranslation } from 'react-i18next';

import { useShallow } from 'zustand/react/shallow';

import { inWechat, wechatLogin } from '@/c-constants/uiConstants';
import { getCourseInfo } from '@/c-api/course';
import {
  EnvStoreState,
  SystemStoreState,
  CourseStoreState,
} from '@/c-types/store';

import { useEnvStore, useCourseStore } from '@/c-store';
import { UserProvider, useUserStore } from '@/store';

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { i18n } = useTranslation();

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

  const { updateCourseName, updateCourseAvatar } = useCourseStore(
    useShallow((state: CourseStoreState) => ({
      updateCourseName: state.updateCourseName,
      updateCourseAvatar: state.updateCourseAvatar,
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
  const currChannel = params.channel || '';
  const isPreviewMode = params.preview
    ? params.preview.toLowerCase() === 'true'
    : false;
  const isSkipMode = params.skip ? params.skip.toLowerCase() === 'true' : false;
  const listenModeEnabled = params.listen
    ? params.listen.toLowerCase() === 'true'
    : false;

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
    if (!wxcodeEnabled || !inWechat()) {
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
    updateShowLearningModeToggle(listenModeEnabled);
    updateLearningMode(listenModeEnabled ? 'listen' : 'read');
  }, [
    isPreviewMode,
    isSkipMode,
    listenModeEnabled,
    updatePreviewMode,
    updateSkip,
    updateShowLearningModeToggle,
    updateLearningMode,
  ]);

  useEffect(() => {
    const fetchCourseInfo = async () => {
      if (!envDataInitialized) return;
      if (courseId) {
        try {
          const resp = await getCourseInfo(courseId, isPreviewMode);
          if (resp) {
            setShowVip(resp.course_price > 0);
            updateCourseName(resp.course_name);
            updateCourseAvatar(resp.course_avatar);
            document.title = resp.course_name + ' - AI 师傅';
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
            const metaKeywords = document.querySelector(
              'meta[name="keywords"]',
            );
            if (metaKeywords) {
              metaKeywords.setAttribute('content', resp.course_keywords);
            } else {
              const newMetaKeywords = document.createElement('meta');
              newMetaKeywords.setAttribute('name', 'keywords');
              newMetaKeywords.setAttribute('content', resp.course_keywords);
              document.head.appendChild(newMetaKeywords);
            }
          } else {
            window.location.href = '/404';
          }
        } catch (error) {
          window.location.href = '/404';
        }
      }
    };
    fetchCourseInfo();
  }, [
    courseId,
    envDataInitialized,
    setShowVip,
    updateCourseName,
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

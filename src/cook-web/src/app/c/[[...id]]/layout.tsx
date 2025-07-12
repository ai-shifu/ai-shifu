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
import { getBoolEnv } from '@/c-utils/envUtils';
import { getCourseInfo } from '@/c-api/course';
import { selectDefaultLanguage } from '@/c-constants/userConstants';
import { EnvStoreState, SystemStoreState, CourseStoreState } from '@/c-types/store';

import { useEnvStore, useCourseStore, UserProvider, useUserStore } from "@/c-store"


const initializeEnvData = async (): Promise<void> => {
  const {
    updateAppId,
    updateCourseId,
    updateAlwaysShowLessonTree,
    updateUmamiWebsiteId,
    updateUmamiScriptSrc,
    updateEruda,
    updateBaseURL,
    updateLogoHorizontal,
    updateLogoVertical,
    updateEnableWxcode,
    updateSiteUrl,
  } = useEnvStore.getState() as EnvStoreState;

  const fetchEnvData = async (): Promise<void> => {
    try {
      const res = await fetch('/api/config', {
        method: 'GET',
        referrer: 'no-referrer',
      });
      if (res.ok) {
        const data = await res.json();
        await updateCourseId(data?.courseId || '');
        await updateAppId(data?.wechatAppId || '');
        await updateAlwaysShowLessonTree(
          data?.alwaysShowLessonTree || 'false'
        );
        await updateUmamiWebsiteId(data?.umamiWebsiteId || '');
        await updateUmamiScriptSrc(data?.umamiScriptSrc || '');
        await updateEruda(data?.enableEruda || 'false');
        await updateBaseURL(data?.apiBaseUrl || '');
        await updateLogoHorizontal(data?.logoHorizontal || '');
        await updateLogoVertical(data?.logoVertical || '');
        await updateEnableWxcode(data?.enableWechatCode?.toString() || 'true');
        await updateSiteUrl(data?.siteHost || '');
      }
    } catch (error) {
      console.error(error)
    } finally {
      const { umamiWebsiteId, umamiScriptSrc } = useEnvStore.getState() as EnvStoreState;
      if (getBoolEnv('eruda')) {
        import('eruda').then((eruda) => eruda.default.init());
      }

      const loadUmamiScript = (): void => {
        if (umamiScriptSrc && umamiWebsiteId) {
          const script = document.createElement('script');
          script.defer = true;
          script.src = umamiScriptSrc;
          script.setAttribute('data-website-id', umamiWebsiteId);
          document.head.appendChild(script);
        }
      };

      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadUmamiScript);
      } else {
        loadUmamiScript();
      }
    }
  };
  await fetchEnvData();
};


export default function ChatLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { i18n } = useTranslation();

  const [envDataInitialized, setEnvDataInitialized] = useState<boolean>(false);
  const [checkWxcode, setCheckWxcode] = useState<boolean>(false);

  useEffect(() => {
    const initialize = async (): Promise<void> => {
      await initializeEnvData();
      setEnvDataInitialized(true);
    };
    initialize();
  }, []);

  const {
    updateChannel,
    channel,
    wechatCode,
    updateWechatCode,
    setShowVip,
    updateLanguage,
    updatePreviewMode,
    updateSkip,
  } = useSystemStore() as SystemStoreState;

  const browserLanguage = selectDefaultLanguage(
    navigator.language || navigator.languages[0]
  );

  const [language] = useState(browserLanguage);

  const courseId = useEnvStore((state: EnvStoreState) => state.courseId);
  const updateCourseId = useEnvStore((state: EnvStoreState) => state.updateCourseId);
  const enableWxcode = useEnvStore((state: EnvStoreState) => state.enableWxcode);

  const { updateCourseName } = useCourseStore(
    useShallow((state: CourseStoreState) => ({
      updateCourseName: state.updateCourseName,
    }))
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
  const isPreviewMode = params.preview ? params.preview.toLowerCase() === 'true' : false;
  const isSkipMode = params.skip ? params.skip.toLowerCase() === 'true' : false;

  if (channel !== currChannel) {
    updateChannel(currChannel);
  }

  useEffect(() => {
    if (!envDataInitialized) return;
    if (enableWxcode && inWechat()) {
      const { appId } = useEnvStore.getState() as EnvStoreState;
      // setLoading(true);
      const currCode = params.code;
      if (!currCode) {
        wechatLogin({
          appId,
        });
        return;
      }
      if (currCode !== wechatCode) {
        updateWechatCode(currCode);
        setCheckWxcode(true);
      }
    } else {
      setCheckWxcode(true);
    }
    // setLoading(false);
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
  }, [isPreviewMode, isSkipMode, updatePreviewMode, updateSkip]);

  useEffect(() => {
    const fetchCourseInfo = async () => {
      if (!envDataInitialized) return;
      if (courseId) {
        try {
          const resp = await getCourseInfo(courseId, isPreviewMode);
          if (resp) {
            setShowVip(resp.course_price > 0);
            updateCourseName(resp.course_name);
            document.title = resp.course_name + ' - AI 师傅'
            const metaDescription = document.querySelector('meta[name="description"]');
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
          } else {
            window.location.href = '/404';
          }
        } catch (error) {
          console.log(error)
          window.location.href = '/404';
        }
      }
    };
    fetchCourseInfo();
  }, [courseId, envDataInitialized, setShowVip, updateCourseName, isPreviewMode]);

  useEffect(() => {
    if (!envDataInitialized) return;
    i18n.changeLanguage(language);
    updateLanguage(language);
  }, [language, envDataInitialized, updateLanguage, i18n]);

  useEffect(() => {
    if (!envDataInitialized) return;
    if (!checkWxcode) return;
    initUser();
  }, [envDataInitialized, checkWxcode, initUser]);

  return (
    <UserProvider>
      {children}
    </UserProvider>
  )
}

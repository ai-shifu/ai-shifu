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
import { userInfoStore } from '@/c-service/storeUtil';
import { getCourseInfo } from '@/c-api/course';
import { selectDefaultLanguage } from '@/c-constants/userConstants';
import { EnvStoreState, SystemStoreState, CourseStoreState } from '@/c-types/store';

import { useEnvStore, useCourseStore, UserProvider } from "@/c-store"


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
      const res = await fetch('/api/config/c-env', {
        method: 'GET',
        referrer: 'no-referrer',
      });
      if (res.ok) {
        const data = await res.json();
        await updateCourseId(data?.NEXT_PUBLIC_COURSE_ID || '');
        await updateAppId(data?.NEXT_PUBLIC_APP_ID || '');
        await updateAlwaysShowLessonTree(
          data?.NEXT_PUBLIC_ALWAYS_SHOW_LESSON_TREE || 'false'
        );
        await updateUmamiWebsiteId(data?.NEXT_PUBLIC_UMAMI_WEBSITE_ID || '');
        await updateUmamiScriptSrc(data?.NEXT_PUBLIC_UMAMI_SCRIPT_SRC || '');
        await updateEruda(data?.NEXT_PUBLIC_ERUDA || 'false');
        await updateBaseURL(data?.NEXT_PUBLIC_BASEURL || '');
        await updateLogoHorizontal(data?.NEXT_PUBLIC_LOGO_HORIZONTAL || '');
        await updateLogoVertical(data?.NEXT_PUBLIC_LOGO_VERTICAL || '');
        await updateEnableWxcode(data?.NEXT_PUBLIC_ENABLE_WXCODE);
        await updateSiteUrl(data?.NEXT_PUBLIC_SITE_URL);
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

  useEffect(() => {
    if (!envDataInitialized) return;
    const userInfo = userInfoStore.get();
    if (userInfo) {
      updateLanguage(userInfo.language);
    } else {
      updateLanguage(browserLanguage);
    }
  }, [browserLanguage, updateLanguage, envDataInitialized]);

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
          if (resp.data) {
            setShowVip(resp.data.course_price > 0);
            updateCourseName(resp.data.course_name);
            document.title = resp.data.course_name + ' - AI 师傅'
            const metaDescription = document.querySelector('meta[name="description"]');
            if (metaDescription) {
              metaDescription.setAttribute('content', resp.data.course_desc);
            } else {
              const newMetaDescription = document.createElement('meta');
              newMetaDescription.setAttribute('name', 'description');
              newMetaDescription.setAttribute('content', resp.data.course_desc);
              document.head.appendChild(newMetaDescription);
            }
            const metaKeywords = document.querySelector('meta[name="keywords"]');
            if (metaKeywords) {
              metaKeywords.setAttribute('content', resp.data.course_keywords);
            } else {
              const newMetaKeywords = document.createElement('meta');
              newMetaKeywords.setAttribute('name', 'keywords');
              newMetaKeywords.setAttribute('content', resp.data.course_keywords);
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
    const checkLogin = async () => {
      // setLoading(true);
      // TODO: FIXME
      // await (useUserStore.getState() as UserStoreState).checkLogin();
      // setLoading(false);
    };
    checkLogin();
  }, [envDataInitialized, checkWxcode]);

  return (
    <UserProvider>
      {children}
    </UserProvider>
  )
}

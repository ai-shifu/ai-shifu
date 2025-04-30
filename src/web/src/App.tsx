import { memo, useEffect, useState } from 'react';
import { parseUrlParams } from 'Utils/urlUtils';
import routes from './Router/index';
import { useRoutes } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import { useSystemStore } from 'stores/useSystemStore';
import i18n from './i18n';
import { inWechat, wechatLogin } from 'constants/uiConstants';
import { getBoolEnv } from 'Utils/envUtils';
import { userInfoStore } from 'Service/storeUtil';
import { getCourseInfo } from './Api/course';
import { useEnvStore } from 'stores/envStore';
import { useUserStore } from 'stores/useUserStore';
import { useShallow } from 'zustand/react/shallow';
import { selectDefaultLanguage } from 'constants/userConstants';
import { useCourseStore } from 'stores/useCourseStore';
import {
  EnvStoreState,
  SystemStoreState,
  CourseStoreState,
  UserStoreState,
} from './types/store';

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
      const res = await fetch('/config/env', {
        method: 'POST',
        referrer: 'no-referrer',
      });
      if (res.ok) {
        const data = await res.json();
        await updateCourseId(data?.REACT_APP_COURSE_ID || '');
        await updateAppId(data?.REACT_APP_APP_ID || '');
        await updateAlwaysShowLessonTree(
          data?.REACT_APP_ALWAYS_SHOW_LESSON_TREE || 'false',
        );
        await updateUmamiWebsiteId(data?.REACT_APP_UMAMI_WEBSITE_ID || '');
        await updateUmamiScriptSrc(data?.REACT_APP_UMAMI_SCRIPT_SRC || '');
        await updateEruda(data?.REACT_APP_ERUDA || 'false');
        await updateBaseURL(data?.REACT_APP_BASEURL || '');
        await updateLogoHorizontal(data?.REACT_APP_LOGO_HORIZONTAL || '');
        await updateLogoVertical(data?.REACT_APP_LOGO_VERTICAL || '');
        await updateEnableWxcode(data?.REACT_APP_ENABLE_WXCODE);
        await updateSiteUrl(data?.REACT_APP_SITE_URL);
      }
    } catch (error) {
    } finally {
      let { umamiWebsiteId, umamiScriptSrc } =
        useEnvStore.getState() as EnvStoreState;
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
const RouterView = () => useRoutes(routes);

const App = () => {
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
    updatePrivewMode,
  } = useSystemStore() as SystemStoreState;

  const browserLanguage = selectDefaultLanguage(
    navigator.language || navigator.languages[0],
  );

  const [language] = useState(browserLanguage);

  const courseId = useEnvStore((state: EnvStoreState) => state.courseId);
  const updateCourseId = useEnvStore(
    (state: EnvStoreState) => state.updateCourseId,
  );
  const enableWxcode = useEnvStore(
    (state: EnvStoreState) => state.enableWxcode,
  );

  const { updateCourseName } = useCourseStore(
    useShallow((state: CourseStoreState) => ({
      updateCourseName: state.updateCourseName,
    })),
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

  const [loading, setLoading] = useState<boolean>(true);
  const params = parseUrlParams() as Record<string, string>;
  const currChannel = params.channel || '';

  if (channel !== currChannel) {
    updateChannel(currChannel);
  }

  useEffect(() => {
    if (!envDataInitialized) return;
    if (enableWxcode && inWechat()) {
      const { appId } = useEnvStore.getState() as EnvStoreState;
      setLoading(true);
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
    setLoading(false);
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
    if (params.previewMode) {
      updatePrivewMode(params.previewMode === 'true');
    }
  }, [params.previewMode, updatePrivewMode]);

  useEffect(() => {
    const fetchCourseInfo = async () => {
      if (!envDataInitialized) return;
      if (courseId) {
        try {
          const resp = await getCourseInfo(courseId);
          if (resp.data) {
            setShowVip(resp.data.course_price > 0);
            updateCourseName(resp.data.course_name);
            document.title = resp.data.course_name + ' - AI 师傅';
            const metaDescription = document.querySelector(
              'meta[name="description"]',
            );
            if (metaDescription) {
              metaDescription.setAttribute('content', resp.data.course_desc);
            } else {
              const newMetaDescription = document.createElement('meta');
              newMetaDescription.setAttribute('name', 'description');
              newMetaDescription.setAttribute('content', resp.data.course_desc);
              document.head.appendChild(newMetaDescription);
            }
            const metaKeywords = document.querySelector(
              'meta[name="keywords"]',
            );
            if (metaKeywords) {
              metaKeywords.setAttribute('content', resp.data.course_keywords);
            } else {
              const newMetaKeywords = document.createElement('meta');
              newMetaKeywords.setAttribute('name', 'keywords');
              newMetaKeywords.setAttribute(
                'content',
                resp.data.course_keywords,
              );
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
  }, [courseId, envDataInitialized, setShowVip, updateCourseName]);

  useEffect(() => {
    if (!envDataInitialized) return;
    i18n.changeLanguage(language);
    updateLanguage(language);
  }, [language, envDataInitialized, updateLanguage]);

  useEffect(() => {
    if (!envDataInitialized) return;
    if (!checkWxcode) return;
    const checkLogin = async () => {
      setLoading(true);
      await (useUserStore.getState() as UserStoreState).checkLogin();
      setLoading(false);
    };
    checkLogin();
  }, [envDataInitialized, checkWxcode]);

  return (
    <ConfigProvider locale={{ locale: language }}>
      {!loading && <RouterView></RouterView>}
    </ConfigProvider>
  );
};

export default memo(App);

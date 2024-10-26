import { memo, useEffect, useState } from 'react';
import { parseUrlParams } from 'Utils/urlUtils.js';
import routes from './Router/index';
import { useRoutes } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import locale from 'antd/locale/zh_CN';
import { useSystemStore } from 'stores/useSystemStore.js';
import i18n from './i18n.js';
import { inWechat, wechatLogin } from 'constants/uiConstants.js';
import { getBoolEnv } from 'Utils/envUtils.js';
import { userInfoStore } from 'Service/storeUtil.js';
import { getCourseInfo } from './Api/course.js';
import { useEnvStore } from 'stores/envStore.js';

const initializeEnvData = async () => {
  const { updateAppId, updateCourseId, updateAlwaysShowLessonTree, updateUmamiWebsiteId, updateUmamiScriptSrc, updateEruda, updateBaseURL } = useEnvStore.getState();
  const fetchEnvData = async () => {
    try {
      const res = await fetch('/config/env', { method: 'POST',referrer:"no-referrer" });
      if (res.ok) {
        const data = await res.json();
        await updateCourseId(data?.REACT_APP_COURSE_ID || "");
        await updateAppId(data?.REACT_APP_APP_ID || "");
        await updateAlwaysShowLessonTree(data?.REACT_APP_ALWAYS_SHOW_LESSON_TREE || "false");
        await updateUmamiWebsiteId(data?.REACT_APP_UMAMI_WEBSITE_ID || "");
        await updateUmamiScriptSrc(data?.REACT_APP_UMAMI_SCRIPT_SRC || "");
        await updateEruda(data?.REACT_APP_ERUDA || "false");
        await updateBaseURL(data?.REACT_APP_BASEURL || "");
      }
    } catch (error) {
    } finally {
      const { courseId, appId, alwaysShowLessonTree, umamiWebsiteId, umamiScriptSrc, eruda } = useEnvStore.getState();
      if (getBoolEnv('eruda')) {
        import('eruda').then(eruda => eruda.default.init());
      }
      // load umami script
      const loadUmamiScript = () => {
        if (umamiScriptSrc && umamiWebsiteId) {
          const script = document.createElement("script");
          script.defer = true;
          script.src = umamiScriptSrc;
          script.setAttribute("data-website-id", umamiWebsiteId);
          document.head.appendChild(script);
        }
      };
      if (document.readyState === 'loading') {
        document.addEventListener("DOMContentLoaded", loadUmamiScript);
      } else {
        loadUmamiScript();
      }
    }
  };
  await fetchEnvData();
};
const RouterView = () => useRoutes(routes);
const App = () => {
  const [envDataInitialized, setEnvDataInitialized] = useState(false);

  useEffect(() => {
    const initialize = async () => {
      await initializeEnvData();
      setEnvDataInitialized(true);
    };
    initialize();
  }, []);

  const { updateChannel, channel, wechatCode, updateWechatCode, setShowVip, updateLanguage } =
    useSystemStore();
  const { courseId, updateCourseId } = useEnvStore.getState();
  const browserLanguage = navigator.language || navigator.languages[0];
  const [language, setLanguage] = useState(browserLanguage);

  useEffect(() => {
    if (!envDataInitialized) return;
    const userInfo = userInfoStore.get();
    if (userInfo) {
      setLanguage(userInfo.language);
    } else {
      updateLanguage(browserLanguage);
    }
  }, [browserLanguage, updateLanguage, envDataInitialized]);

  const [loading, setLoading] = useState(true);
  const params = parseUrlParams();
  const currChannel = params.channel || '';

  if (channel !== currChannel) {
    updateChannel(currChannel);
  }

  useEffect(() => {
    if (!envDataInitialized) return;
    if (inWechat()) {
      const { appId } = useEnvStore.getState();
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
      }
    }
    setLoading(false);
  }, [params.code, updateWechatCode, wechatCode, envDataInitialized]);

  useEffect(() => {
    const fetchCourseInfo = async () => {
      if (!envDataInitialized) return;
      let id = courseId;
      if (params.courseId) {
        await updateCourseId(params.courseId);
        id = params.courseId;
      }
      const resp = await getCourseInfo(id);
      if (resp.data.course_id !== courseId) {
        await updateCourseId(resp.data.course_id);
      }
      setShowVip(resp.data.course_price > 0);
    };
    fetchCourseInfo();
  }, [envDataInitialized]);

  // mount debugger
  useEffect(() => {
    if (!envDataInitialized) return;
    window.ztDebug = {};
    return () => {
      delete window.ztDebug;
    };
  }, [envDataInitialized]);

  useEffect(() => {
    if (!envDataInitialized) return;
    i18n.changeLanguage(language);
    updateLanguage(language);
  }, [language, envDataInitialized]);

  return (
    <ConfigProvider locale={locale}>
      {!loading && <RouterView></RouterView>}
    </ConfigProvider>
  );
};

export default memo(App);

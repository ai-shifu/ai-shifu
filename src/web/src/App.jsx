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


// load umami script
document.addEventListener("DOMContentLoaded", function() {
  const scriptSrc = process.env.REACT_APP_UMAMI_SCRIPT_SRC;
  const dataId = process.env.REACT_APP_UMAMI_WEBSITE_ID;
  if (scriptSrc && dataId) {
    const script = document.createElement("script");
    script.defer = true;
    script.src = scriptSrc;
    script.setAttribute("data-website-id", dataId);
    document.head.appendChild(script);
  }
});
if (getBoolEnv('REACT_APP_ERUDA')) {
  import('eruda').then(eruda => eruda.default.init());
}

const RouterView = () => useRoutes(routes);

const App = () => {
  // get browser language
  const { updateChannel, channel, wechatCode, updateWechatCode, courseId, updateCourseId, setShowVip, updateLanguage } =
    useSystemStore();
  // get browser language
  const browserLanguage = navigator.language || navigator.languages[0];
  const [language, setLanguage] = useState(browserLanguage);

  useEffect(() => {
    const userInfo = userInfoStore.get();
    if (userInfo) {
      setLanguage(userInfo.language);
    } else {
      updateLanguage(browserLanguage);
    }
  }, [browserLanguage, updateLanguage]);

  const [loading, setLoading] = useState(true);
  const params = parseUrlParams();
  const currChannel = params.channel || '';

  if (channel !== currChannel) {
    updateChannel(currChannel);
  }

  useEffect(() => {
    if (inWechat()) {
      setLoading(true);
      const currCode = params.code;
      if (!currCode) {
        wechatLogin({
          appId: process.env.REACT_APP_APP_ID,
        });
        return;
      }
      if (currCode !== wechatCode) {
        updateWechatCode(currCode);
      }
    }
    setLoading(false);
  }, [params.code, updateWechatCode, wechatCode]);

  useEffect(() => {
    let id = courseId;
    if (params.courseId) {
      updateCourseId(params.courseId);
      id = params.courseId;
    }
    getCourseInfo(id).then((resp) => {
      setShowVip(resp.data.course_price > 0);
    });
  }, []);

  // mount debugger
  useEffect(() => {
    window.ztDebug = {};
    return () => {
      delete window.ztDebug;
    };
  });

  useEffect(() => {
    i18n.changeLanguage(language);
    updateLanguage(language);
  }, [language]);

  return (
    <ConfigProvider locale={locale}>
      {!loading && <RouterView></RouterView>}
    </ConfigProvider>
  );
};

export default memo(App);

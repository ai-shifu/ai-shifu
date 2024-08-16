import { useEffect } from 'react';
import routes from "./Router/index";
import { useRoutes } from "react-router-dom";
import { ConfigProvider } from "antd";
import locale from "antd/locale/zh_CN";
import { useSystemStore } from 'stores/useSystemStore.js'; 
import i18n from './i18n.js';

const RouterView = () => useRoutes(routes);

const App = () => {
  const { language } = useSystemStore((state) => state);

  // 挂载 debugger
  useEffect(() => {
    window.ztDebug = {};

    return () => {
      delete window.ztDebug;
    }
  })

  useEffect(() => {
    i18n.changeLanguage(language);
  }, [language])

  
  return (
    <ConfigProvider locale={locale}>
      <RouterView></RouterView>
    </ConfigProvider>
  );
};

export default App;

import styles from './PrivacyPolicyPage.module.scss';
import ReactMarkdown from 'react-markdown';
import zhContent from './Contents/zh_Cn_PrivacyPlolicyContent.md';
import enContent from './Contents/en_PrivacyPlolicyContent.md';
import { useSystemStore } from 'stores/useSystemStore';
import { userInfoStore } from 'Service/storeUtil';
import { useEffect } from 'react';

const contents = {
  'zh-CN': zhContent,
  'en-US': enContent,
  en: enContent,
};

export const PrivacyPolicyPage = () => {
  const { language, updateLanguage } = useSystemStore();
  useEffect(() => {
    const userInfo = userInfoStore.get();
    if (userInfo) {
      updateLanguage(userInfo.language);
    }
  }, [updateLanguage]);
  const markdown = contents[language];
  return (
    <div className={styles.PrivacyPolicyPage}>
      <ReactMarkdown children={markdown} />
    </div>
  );
};

export default PrivacyPolicyPage;

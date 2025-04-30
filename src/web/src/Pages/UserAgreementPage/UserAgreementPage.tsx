import styles from './UserAgreementPage.module.scss';
import ReactMarkdown from 'react-markdown';
import zhCNAggreement from './Contents/zh_CN_aggreement.md';
import enAggreement from './Contents/en_aggreement.md';
import { useSystemStore } from 'stores/useSystemStore';
import { useEffect } from 'react';
import { userInfoStore } from 'Service/storeUtil';
const aggreements = {
  'zh-CN': zhCNAggreement,
  'en-US': enAggreement,
  en: enAggreement,
};

export const UserAgreementPage = () => {
  const { language, updateLanguage } = useSystemStore();
  const markdown = aggreements[language];

  useEffect(() => {
    const userInfo = userInfoStore.get();
    if (userInfo) {
      updateLanguage(userInfo.language);
    }
  }, [updateLanguage]);

  return (
    <div className={styles.UserAgreementPage}>
      <ReactMarkdown children={markdown} />
    </div>
  );
};

export default UserAgreementPage;

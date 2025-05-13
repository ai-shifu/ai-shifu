import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from 'antd';
import styles from './NotFoundPage.module.scss';
import logo from 'Assets/logos/logo-color-392.png';
import { useEnvStore } from 'stores/envStore';

const NotFoundPage = () => {
  const { t } = useTranslation();
  const siteUrl = useEnvStore((state) => state.siteUrl);

  const handleBackToHome = () => {
    if (siteUrl) {
      window.location.href = siteUrl;
    } else {
      // Default fallback if siteUrl is not set
      window.location.href = '/c/';
    }
  };

  return (
    <div className={styles.notFoundPage}>
      <div className={styles.content}>
        <div className={styles.inline}>
          <img src={logo} alt="logo" />
          <h1>404</h1>
        </div>
        <p>{t('error.pageNotFound')}</p>
        <Button type="primary" onClick={handleBackToHome}>
          {t('common.backToHome')}
        </Button>
      </div>
    </div>
  );
};

export default memo(NotFoundPage);

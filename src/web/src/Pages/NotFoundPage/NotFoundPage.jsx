import { memo, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from 'antd';
import { useNavigate } from 'react-router-dom';
import styles from './NotFoundPage.module.scss';
import logoColor from 'Assets/logos/logo-color-392.png'

const NotFoundPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [countdown, setCountdown] = useState(5);

  useEffect(() => {
    if (countdown === 0) {
      navigate('/');
    }
    const timer = setTimeout(() => {
      setCountdown(countdown - 1);
    }, 1000);

    return () => clearTimeout(timer);
  }, [countdown, navigate]);

  return (
    <div className={styles.notFoundPage}>
      <div className={styles.content}>
        <div className={styles.inline}>
          <img src={logoColor} alt="logo" />
          <h1>404</h1>
        </div>
        <p>{t('error.pageNotFound')}</p>
        <p>{t('common.redirectInSeconds', { seconds: countdown })}</p>
        <Button
          type="primary"
          onClick={() => navigate('/')}
        >
          {t('common.backToHome')}
        </Button>
      </div>
    </div>
  );
};

export default memo(NotFoundPage);

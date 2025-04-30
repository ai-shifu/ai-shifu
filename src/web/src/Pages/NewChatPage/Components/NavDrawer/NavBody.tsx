import styles from './NavBody.module.scss';
import MainButton from 'Components/MainButton';
import { useTranslation } from 'react-i18next';
import { memo } from 'react';
import LogoWithText from 'Components/logo/LogoWithText';

export const NavBody = ({ onLoginClick = () => {} }) => {
  const { t } = useTranslation();
  return (
    <div className={styles.navBody}>
      <LogoWithText size={100} color="color" direction="col" />
      <div className={styles.btnWrapper}>
        <MainButton width={185} onClick={() => onLoginClick?.()}>
          {t('user.loginMainButton')}
        </MainButton>
      </div>
    </div>
  );
};

export default memo(NavBody);

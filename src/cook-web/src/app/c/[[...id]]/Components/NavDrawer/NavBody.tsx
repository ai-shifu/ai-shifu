import styles from './NavBody.module.scss';
import MainButton from '@/c-components/MainButton';
import { useTranslation } from 'react-i18next';
import { memo } from 'react';
import LogoWithText from '@/c-components/logo/LogoWithText';

export const NavBody = ({
  onLoginClick = () => {},
}) => {
  const { t } = useTranslation('translation', { keyPrefix: 'c' });
  return (<div className={styles.navBody}>
    <LogoWithText size={100} direction='col' />
    <div className={styles.btnWrapper}>
      <MainButton width={185} onClick={() => onLoginClick?.()}>
        {t('user.loginMainButton')}
      </MainButton>
    </div>
  </div>)
}

export default memo(NavBody);

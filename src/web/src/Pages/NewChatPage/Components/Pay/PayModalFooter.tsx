import { memo } from 'react';
import styles from './PayModalFooter.module.scss';
import classNames from 'classnames';
import { useTranslation } from 'react-i18next';
export const PayModalFooter = ({ className }) => {
  const { t } = useTranslation();
  return (
    <div className={classNames(styles.protocalWrapper, className)}>
      <div className={styles.protocalDesc}>{t('pay.protocalDesc')}</div>
      <div className={styles.protocalLinks}>
        <a
          className={styles.protocalLink}
          href="/useragreement"
          target="_blank"
          referrerPolicy="no-referrer"
        >
          {t('pay.modelServiceAgreement')}
        </a>
        <a
          className={styles.protocalLink}
          href="/privacypolicy"
          target="_blank"
          referrerPolicy="no-referrer"
        >
          {t('pay.userPrivacyPolicy')}
        </a>
      </div>
    </div>
  );
};

export default memo(PayModalFooter);

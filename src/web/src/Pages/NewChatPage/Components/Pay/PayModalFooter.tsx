import { memo } from 'react';
import styles from './PayModalFooter.module.scss';
import classNames from 'classnames';
import { useTranslation } from 'react-i18next';
export const PayModalFooter = ({ className }) => {
  const { t } = useTranslation();
  return (
    <div className={classNames(styles.protocolWrapper, className)}>
      <div className={styles.protocolDesc}>{t('pay.protocolDesc')}</div>
      <div className={styles.protocolLinks}>
        <a
          className={styles.protocolLink}
          href="/useragreement"
          target="_blank"
          referrerPolicy="no-referrer"
        >
          {t('pay.modelServiceAgreement')}
        </a>
        <a
          className={styles.protocolLink}
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

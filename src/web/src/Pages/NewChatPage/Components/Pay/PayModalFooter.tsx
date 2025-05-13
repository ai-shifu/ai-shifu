import { memo } from 'react';
import styles from './PayModalFooter.module.scss';
import classNames from 'classnames';
import { useTranslation } from 'react-i18next';

export const PayModalFooter = ({ className }) => {
  const { t } = useTranslation();

  const renderVirtualProductPoint1 = () => {
    const point1Text = t('pay.virtualProductPoint1');
    const parts = point1Text.split(/\{\{modelServiceAgreement\}\}|\{\{userPrivacyPolicy\}\}/g);

    if (parts.length !== 3) {
      return point1Text;
    }

    return (
      <>
        {parts[0]}
        <a
          className={styles.protocolLink}
          href="/useragreement"
          target="_blank"
          referrerPolicy="no-referrer"
          rel="noopener"
        >
          {t('pay.modelServiceAgreement')}
        </a>{parts[1]}<a
          className={styles.protocolLink}
          href="/privacypolicy"
          target="_blank"
          referrerPolicy="no-referrer"
          rel="noopener"
        >
          {t('pay.userPrivacyPolicy')}
        </a>
        {parts[2]}
      </>
    );
  };

  return (
    <div className={classNames(styles.protocolWrapper, className)}>
      <div className={styles.virtualProductDesc}>
        <div className={styles.descTitle}>{t('pay.virtualProductDesc')}</div>
        <div className={styles.descPoint}>{renderVirtualProductPoint1()}</div>
        <div className={styles.descPoint}>{t('pay.virtualProductPoint2')}</div>
      </div>
    </div>
  );
};

export default memo(PayModalFooter);

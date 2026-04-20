import { memo } from 'react';
import styles from './PayModalFooter.module.scss';
import classNames from 'classnames';
import { Trans, useTranslation } from 'react-i18next';

export const PayModalFooter = ({ className = '' }) => {
  const { t } = useTranslation();

  const renderVirtualProductPoint1 = () => {
    return (
      <Trans
        i18nKey='module.pay.virtualProductPoint1'
        components={{
          modelServiceAgreement: (
            <a
              className={styles.protocolLink}
              href='/useragreement'
              target='_blank'
              referrerPolicy='no-referrer'
              rel='noopener'
            />
          ),
          userPrivacyPolicy: (
            <a
              className={styles.protocolLink}
              href='/privacypolicy'
              target='_blank'
              referrerPolicy='no-referrer'
              rel='noopener'
            />
          ),
        }}
        values={{
          modelServiceAgreement: t('module.pay.modelServiceAgreement'),
          userPrivacyPolicy: t('module.pay.userPrivacyPolicy'),
        }}
      />
    );
  };

  return (
    <div className={classNames(styles.protocolWrapper, className)}>
      <div className={styles.virtualProductDesc}>
        <div className={styles.descTitle}>
          {t('module.pay.virtualProductDesc')}
        </div>
        <div className={styles.descPoint}>{renderVirtualProductPoint1()}</div>
        <div className={styles.descPoint}>
          {t('module.pay.virtualProductPoint2')}
        </div>
      </div>
    </div>
  );
};

export default memo(PayModalFooter);

import { memo } from 'react';
import styles from './PayModalFooter.module.scss';
import classNames from 'classnames';
import { useTranslation } from 'react-i18next';
export const PayModalFooter = ({ className }) => {
  const { t } = useTranslation();
  return (
    <div className={classNames(styles.protocalWrapper, className)}>
      <div className={styles.numberedList}>
        <div className={styles.listTitle}>说明：</div>
        <div className={styles.listItem}>
          <span className={styles.listNumber}>1.</span>
          <span>{t('pay.protocalDesc')}</span>
        </div>
        <div className={styles.protocalLinks}>
          <a
            className={styles.protocalLink}
            href="/useraggrement"
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
        <div className={styles.listItem}>
          <span className={styles.listNumber}>2.</span>
          <span>{t('pay.virtualGoodsNotice')}</span>
        </div>
      </div>
    </div>
  );
};

export default memo(PayModalFooter);

import PopupModal from 'Components/PopupModal';
import { Button } from 'antd';

import styles from './FilingModal.module.scss';
import { memo } from 'react';
import { useTranslation } from 'react-i18next';

export const FillingModal = ({
  open,
  onClose,
  style,
  onFeedbackClick,
  className,
}) => {
  const { t } = useTranslation();
  return (
    <PopupModal
      open={open}
      onClose={onClose}
      wrapStyle={{ ...style }}
      className={className}
    >
      <div className={styles.filingModal}>
        <div>{t('common.companyName')}</div>
        <div>{t('common.companyAddress')}</div>
        <div>
          <a
            className={styles.miitLink}
            href="https://beian.miit.gov.cn/"
            target="_blank"
            rel="noreferrer"
          >
            {t('navigation.icp')}
          </a>
        </div>
        <div className={styles.gonganRow}>
          <img
            className={styles.beianIcon}
            src={require('@Assets/newchat/light/beian.png')}
            alt={t('navigation.filing')}
          />
          <div>{t('navigation.gongan')}</div>
        </div>
        <div className={styles.btnGroup}>
          <Button
            type="link"
            className={styles.actionBtn}
            onClick={onFeedbackClick}
          >
            {t('navigation.feedbackTitle')}
          </Button>
          <div>|</div>
          <Button
            type="link"
            className={styles.actionBtn}
            onClick={(e) => {
              window.open('/useragreement');
            }}
          >
            {t('navigation.userAgreement')}
          </Button>
          <div>|</div>
          <Button
            type="link"
            className={styles.actionBtn}
            onClick={(e) => {
              window.open('/privacypolicy');
            }}
          >
            {t('navigation.privacyPolicy')}
          </Button>
        </div>
      </div>
    </PopupModal>
  );
};

export default memo(FillingModal);

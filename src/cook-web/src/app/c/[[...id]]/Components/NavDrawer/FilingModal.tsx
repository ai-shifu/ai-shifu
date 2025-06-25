import styles from './FilingModal.module.scss';

import { memo } from 'react';
import { useTranslation } from 'react-i18next';

import PopupModal from '@/c-components/PopupModal';
import { Button } from '@/components/ui/button';

import Image from 'next/image';
import imgBeian from '@/c-assets/newchat/light/beian.png'

export const FillingModal = ({
  open,
  onClose,
  style,
  onFeedbackClick,
  className,
}) => {
  const { t } = useTranslation('translation', {keyPrefix: 'c'});

  return (
    // @ts-expect-error EXPECT
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
          <Image
            className={styles.beianIcon}
            src={imgBeian.src}
            alt={t('navigation.filing')}
          />
          <div>{t('navigation.gongan')}</div>
        </div>
        <div className={styles.btnGroup}>
          <Button
            variant="link"
            className={styles.actionBtn}
            onClick={onFeedbackClick}
          >
            {t('navigation.feedbackTitle')}
          </Button>
          <div>|</div>
          <Button
            variant="link"
            className={styles.actionBtn}
            onClick={() => {
              window.open('/useragreement');
            }}
          >
            {t('navigation.userAgreement')}
          </Button>
          <div>|</div>
          <Button
            variant="link"
            className={styles.actionBtn}
            onClick={() => {
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

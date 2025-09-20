import styles from './SettingBaseModal.module.scss';

import { memo, useContext } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

import { calModalWidth } from '@/c-utils/common';
import { AppContext } from '@/c-components/AppContext';

import { Button } from '@/components/ui/Button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/Dialog';

export const SettingBaseModal = ({
  open,
  children,
  onOk,
  onClose,
  defaultWidth = '360px',
  title,
  header = (t, title) => <div className={styles.header}>{title}</div>,
}) => {
  const { t } = useTranslation();

  const { mobileStyle } = useContext(AppContext);

  function handleOpenChange(open: boolean) {
    if (!open) {
      onClose?.();
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
    >
      <DialogContent className={cn(styles.SettingBaseModal)}>
        <DialogHeader>
          <DialogTitle>{title || t('common.settings')}</DialogTitle>
        </DialogHeader>
        <div
          style={{
            width: calModalWidth({
              inMobile: mobileStyle,
              width: defaultWidth,
            }),
          }}
          className={styles.modalWrapper}
        >
          {header(t, title || t('common.settings'))}
          {children}
          <div className={styles.btnWrapper}>
            <Button
              className={cn('w-full')}
              onClick={onOk}
            >
              {t('common.ok')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default memo(SettingBaseModal);

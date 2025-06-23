import styles from './ShortcutModal.module.scss';
import { memo, useContext } from 'react';
import { useShallow } from 'zustand/react/shallow';
import clsx from 'clsx';
// import { Modal } from 'antd';
import { Dialog, DialogContent, DialogTrigger } from '@radix-ui/react-dialog';

import { AppContext } from '@/c-components/AppContext';
import { calModalWidth } from '@/c-utils/common';
import { useUiLayoutStore } from '@/c-store/useUiLayoutStore';
import { useTranslation } from 'react-i18next';
import { shortcutKeys } from '@/c-service/shortcut';

const ShortcutModal = ({ open, onClose }) => {
  const { mobileStyle } = useContext(AppContext);
  const { inMacOs } = useUiLayoutStore(
    useShallow((state) => ({ inMacOs: state.inMacOs }))
  );
  const { t } = useTranslation('translation', { keyPrefix: 'c'});
  
  const shortcutKeysOptions = shortcutKeys.map((v) => ({
    id: v.id,
    title: t(`common.shortcut.title.${v.id}`),
    keys: (inMacOs ? v.macKeys : v.keys).map((v) => {
      return t(`common.shortcut.key.${v}`)
    }),
  }))

  const getShortcutKey = (keyText, index) => {
    const isSingleText = keyText.length === 1;

    return (
      <div
        key={index}
        className={clsx(
          styles.shortcutKey,
          isSingleText ? styles.singleText : styles.multiText
        )}
      >
        {keyText}
      </div>
    );
  };

  return (
    <>
      <Dialog open={open} onOpenChange={(open) => {
        if (!open) {
          onClose()
        }
      }}>
        <DialogContent>
          <div className={styles.shortcutTitle}>
            键盘快捷方式
          </div>
          <div className={styles.shortcutContent}>
            {shortcutKeysOptions.map((option, index) => {
              return (
                <div className={styles.shortcutRow} key={option.title}>
                  <div className={styles.rowTitle}>{option.title}</div>
                  <div className={styles.rowKeys}>
                    {option.keys.map((v, i) => {
                      return getShortcutKey(v, i);
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </DialogContent>
      </Dialog>
      {/* <Modal
        className={styles.shortcutModal}
        width={calModalWidth({ mobileStyle, width: '400px' })}
        open={open}
        footer={null}
        maskClosable={true}
        onCancel={onClose}
      >
        <div></div>
      </Modal> */}
    </>
  );
};

export default memo(ShortcutModal);

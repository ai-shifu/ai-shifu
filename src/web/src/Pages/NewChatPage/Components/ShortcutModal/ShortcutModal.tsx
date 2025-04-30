import { memo, useContext } from 'react';
import { useShallow } from 'zustand/react/shallow';
import classNames from 'classnames';
import { Modal } from 'antd';
import styles from './ShortcutModal.module.scss';
import { AppContext } from 'Components/AppContext';
import { calModalWidth } from 'Utils/common';
import { useUiLayoutStore } from 'stores/useUiLayoutStore';
import { useTranslation } from 'react-i18next';
import { shortcutKeys } from 'Service/shortcut';

const ShortcutModal = ({ open, onClose }) => {
  const { mobileStyle } = useContext(AppContext);
  const { inMacOs } = useUiLayoutStore(
    useShallow((state) => ({ inMacOs: state.inMacOs })),
  );
  const { t } = useTranslation();
  const shortcutKeysOptions = shortcutKeys.map((v) => ({
    id: v.id,
    title: t(`common.shortcut.title.${v.id}`),
    keys: (inMacOs ? v.macKeys : v.keys).map((v) => {
      return t(`common.shortcut.key.${v}`);
    }),
  }));

  const getShortcutKey = (keyText, index) => {
    const isSingleText = keyText.length === 1;

    return (
      <div
        key={index}
        className={classNames(
          styles.shortcutKey,
          isSingleText ? styles.singleText : styles.multiText,
        )}
      >
        {keyText}
      </div>
    );
  };

  return (
    <Modal
      className={styles.shortcutModal}
      width={calModalWidth({ mobileStyle, width: '400px' })}
      open={open}
      footer={null}
      maskClosable={true}
      onCancel={onClose}
    >
      <div>
        <div className={styles.shortcutTitle}>键盘快捷方式</div>
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
      </div>
    </Modal>
  );
};

export default memo(ShortcutModal);

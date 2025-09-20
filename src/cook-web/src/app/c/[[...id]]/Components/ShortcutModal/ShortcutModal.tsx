import styles from './ShortcutModal.module.scss';
import { memo } from 'react';
import { useShallow } from 'zustand/react/shallow';
import clsx from 'clsx';

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';

import { useUiLayoutStore } from '@/c-store/useUiLayoutStore';

const ShortcutModal = ({ open, onClose }) => {
  const { inMacOs } = useUiLayoutStore(
    useShallow(state => ({ inMacOs: state.inMacOs })),
  );

  const shortcutKeysOptions = [
    {
      id: 'continue',
      title: '继续（无需用户输入或选择时）',
      keys: ['空格']
    },
    {
      id: 'ask',
      title: '追问',
      keys: inMacOs ? ['⌘', '⇧', 'A'] : ['Ctrl', '⇧', 'A']
    },
    {
      id: 'shortcut',
      title: '显示快捷方式',
      keys: inMacOs ? ['⌘', '/'] : ['Ctrl', '/']
    }
  ];

  const getShortcutKey = (keyText: string, index: number) => {
    const isSingleText = keyText.length === 1;

    return (
      <div
        key={index}
        className={clsx(
          styles.shortcutKey,
          isSingleText ? styles.singleText : styles.multiText,
        )}
      >
        {keyText}
      </div>
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={open => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogContent className={styles.shortcutModal}>
        <DialogHeader>
          <DialogTitle className={styles.shortcutTitle}>
            快捷键
          </DialogTitle>
        </DialogHeader>
        <div className={styles.shortcutContent}>
          {shortcutKeysOptions.map(option => {
            return (
              <div
                className={styles.shortcutRow}
                key={option.title}
              >
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
  );
};

export default memo(ShortcutModal);

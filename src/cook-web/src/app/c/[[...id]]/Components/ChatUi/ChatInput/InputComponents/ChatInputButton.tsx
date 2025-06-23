import styles from './ChatInputButton.module.scss';
import { memo, useEffect } from 'react';

import {
  INTERACTION_OUTPUT_TYPE,
  INTERACTION_TYPE,
} from '@/c-constants/courseConstants';

import MainButton from '@/c-components/MainButton';
import { registerInteractionType } from '../interactionRegistry';
import { useShallow } from 'zustand/react/shallow';
import { useUiLayoutStore } from '@/c-store/useUiLayoutStore';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useHotkeys } from 'react-hotkeys-hook';
import { SHORTCUT_IDS, genHotKeyIdentifier } from '@/c-service/shortcut';


export const ChatInputButton = ({ type, props, onClick, disabled }) => {
  const { skip } = useSystemStore(
    useShallow((state) => ({ skip: state.skip }))
  );

  const onBtnClick = () => {
    if (type === INTERACTION_TYPE.NEXT_CHAPTER) {
      onClick?.(INTERACTION_OUTPUT_TYPE.NEXT_CHAPTER, false, {
        lessonId: props.lessonId,
      });
      return;
    }

    if (type === INTERACTION_TYPE.ORDER) {
      onClick?.(INTERACTION_OUTPUT_TYPE.ORDER, false, { orderId: props.value });
      return
    }
    if (type === INTERACTION_TYPE.NONBLOCK_ORDER) {
      onClick?.(INTERACTION_OUTPUT_TYPE.NONBLOCK_ORDER, false, { orderId: props.value });
      return
    }
    if (type === INTERACTION_TYPE.REQUIRE_LOGIN) {
      onClick?.(INTERACTION_OUTPUT_TYPE.REQUIRE_LOGIN,false, props.value);
      return;
    }

    onClick?.(INTERACTION_OUTPUT_TYPE.CONTINUE, props.display !== undefined ? props.display : false, props.value);
  }

  useEffect(() => {
    if (skip && !disabled && (type === INTERACTION_TYPE.NEXT_CHAPTER || type === INTERACTION_TYPE.CONTINUE )) {
      onBtnClick();
    }
  }, [skip, disabled, type]);

  const { inMacOs } = useUiLayoutStore(
    useShallow((state) => ({ inMacOs: state.inMacOs }))
  );

  useHotkeys(
    `${genHotKeyIdentifier(SHORTCUT_IDS.CONTINUE, inMacOs)}, enter`,
    () => {
      onBtnClick();
    },
    [onBtnClick]
  );

  return (
    <div className={styles.continueWrapper}>
      <MainButton
        className={styles.continueBtn}
        width="90%"
        disabled={disabled}
        onClick={onBtnClick}
      >
        {props.label}
      </MainButton>
    </div>
  );
};

const ChatInputButtonMemo = memo(ChatInputButton);
registerInteractionType(INTERACTION_TYPE.CONTINUE, ChatInputButtonMemo);
registerInteractionType(INTERACTION_TYPE.NEXT_CHAPTER, ChatInputButtonMemo);
registerInteractionType(INTERACTION_TYPE.ORDER, ChatInputButtonMemo);
registerInteractionType(INTERACTION_TYPE.NONBLOCK_ORDER, ChatInputButtonMemo);
registerInteractionType(INTERACTION_TYPE.REQUIRE_LOGIN, ChatInputButtonMemo);
export default ChatInputButtonMemo;

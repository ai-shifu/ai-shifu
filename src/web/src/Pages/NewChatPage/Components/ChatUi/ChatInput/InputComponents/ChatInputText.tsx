import { useState, useEffect } from 'react';
import { message } from 'antd';
import { Input } from '@chatui/core';
import { useTranslation } from 'react-i18next';
import {
  INTERACTION_TYPE,
  INTERACTION_OUTPUT_TYPE,
} from 'constants/courseConstants';

import styles from './ChatInputText.module.scss';
import { memo } from 'react';
import { registerInteractionType } from '../interactionRegistry';

const OUTPUT_TYPE_MAP = {
  [INTERACTION_TYPE.INPUT]: INTERACTION_OUTPUT_TYPE.TEXT,
  [INTERACTION_TYPE.PHONE]: INTERACTION_OUTPUT_TYPE.PHONE,
  [INTERACTION_TYPE.CHECKCODE]: INTERACTION_OUTPUT_TYPE.CHECKCODE,
};

export const ChatInputText = ({
  onClick,
  type,
  disabled = false,
  props = {},
}) => {
  const { t } = useTranslation();
  const [input, setInput] = useState('');
  const [messageApi, contextHolder] = message.useMessage();

  const outputType = OUTPUT_TYPE_MAP[type];

  const onSendClick = async () => {
    if (input.trim() === '') {
      messageApi.warning(t('chat.chatInputWarn'));
      return;
    }

    onClick?.(outputType, true, input.trim());
    setInput('');
  };

  useEffect(() => {
    if (!disabled) {
      const elem = document.querySelector(`.${styles.inputField}`);

      if (elem) {
        elem.focus();
      }
    }
  }, [disabled]);

  return (
    <div className={styles.inputTextWrapper}>
      <div className={styles.inputForm}>
        <div className={styles.inputWrapper}>
          <Input
            autoSize={{ minRows: 1, maxRows: 5 }}
            type="text"
            value={input}
            onChange={(v) => {
              let newValue = v;
              if (newValue.endsWith('\n')) {
                newValue = newValue.slice(0, -1);
              }
              setInput(newValue);
            }}
            placeholder={
              props?.content?.content || t('chat.chatInputPlaceholder')
            }
            className={styles.inputField}
            disabled={disabled}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                onSendClick();
              }
            }}
          ></Input>
          <img
            src={require('@Assets/newchat/light/icon-send.png')}
            alt=""
            className={styles.sendIcon}
            onClick={onSendClick}
          />
        </div>
        {contextHolder}
      </div>
    </div>
  );
};

const ChatInputTextMemo = memo(ChatInputText);
registerInteractionType(INTERACTION_TYPE.INPUT, ChatInputTextMemo);
registerInteractionType(INTERACTION_TYPE.PHONE, ChatInputTextMemo);
registerInteractionType(INTERACTION_TYPE.CHECKCODE, ChatInputTextMemo);
export default ChatInputTextMemo;

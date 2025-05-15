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

interface ChatInputProps {
  onClick?: (outputType: string, isValid: boolean, value: string) => void;
  type?: string;
  disabled?: boolean;
  props?: {
    content?: {
      content?: string;
    };
  };
}

export const ChatInputText = ({ onClick, type, disabled = false, props = {} }: ChatInputProps) => {
  const {t}= useTranslation();
  const [input, setInput] = useState('');
  const [messageApi, contextHolder] = message.useMessage();
  const [isComposing, setIsComposing] = useState(false);

  const outputType = OUTPUT_TYPE_MAP[type];

  const onSendClick = async () => {
    if (input.trim() === '') {
      messageApi.warning(t('chat.chatInputWarn'));
      return;
    }

    onClick?.(outputType, true,input.trim());
    setInput('');
  };

  useEffect(() => {
    if (!disabled) {
      const elem = document.querySelector(`.${styles.inputField}`) as HTMLTextAreaElement;
      if (elem) {
        elem.focus();
      }
    }
  }, [disabled]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // 如果正在输入中文，不处理任何键盘事件
    if (isComposing) {
      return;
    }

    if (e.key === 'Enter') {
      if (e.shiftKey) {
        // Shift + Enter 允许换行
        return;
      } else {
        // 普通 Enter 发送消息
        e.preventDefault();
        onSendClick();
      }
    }
  };

  return (
    <div className={styles.inputTextWrapper}>
      <div className={styles.inputForm}>
        <div className={styles.inputWrapper}>
          <Input
            multiline
            rows={1}
            maxRows={5}
            type="text"
            value={input}
            onChange={(v) => {
              setInput(v);
            }}
            placeholder={props?.content?.content || t('chat.chatInputPlaceholder')}
            className={styles.inputField}
            disabled={disabled}
            onKeyDown={handleKeyDown}
            onCompositionStart={() => setIsComposing(true)}
            onCompositionEnd={() => setIsComposing(false)}
          >
          </Input>
          <img src={require('@Assets/newchat/light/icon-send.png')} alt="" className={styles.sendIcon} onClick={onSendClick} />
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

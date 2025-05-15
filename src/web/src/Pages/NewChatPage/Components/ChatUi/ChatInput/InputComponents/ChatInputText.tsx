import { useState, useEffect, useRef } from 'react';
import { message } from 'antd';
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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const placeholder = props?.content?.content || t('chat.chatInputPlaceholder');

  const outputType = OUTPUT_TYPE_MAP[type];

  const onSendClick = async () => {
    if (input.trim() === '') {
      messageApi.warning(t('chat.chatInputWarn'));
      return;
    }

    onClick?.(outputType, true,input.trim());
    setInput('');

    // 重置高度
    if (textareaRef.current) {
      textareaRef.current.style.height = '24px';
    }
  };

  const adjustHeight = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    // 保存当前值和placeholder
    const currentValue = textarea.value;
    const currentPlaceholder = textarea.placeholder;

    // 如果当前没有输入值，临时设置值为placeholder来计算高度
    if (!currentValue) {
      textarea.value = currentPlaceholder;
    }

    textarea.style.height = 'auto';
    const newHeight = Math.min(textarea.scrollHeight-20, 120);
    textarea.style.height = `${newHeight}px`;

    // 恢复原始状态
    if (!currentValue) {
      textarea.value = '';
      textarea.placeholder = currentPlaceholder;
    }
  };

  useEffect(() => {
    if (!disabled && textareaRef.current) {
      textareaRef.current.focus();
      // 初始化时计算高度
      adjustHeight();
    }
  }, [disabled]);

  // 当 placeholder 改变时重新计算高度
  useEffect(() => {
    adjustHeight();
  }, [placeholder]);

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);
    adjustHeight();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (isComposing) {
      return;
    }

    if (e.key === 'Enter') {
      if (e.shiftKey) {
        return;
      } else {
        e.preventDefault();
        onSendClick();
      }
    }
  };

  return (
    <div className={styles.inputTextWrapper}>
      <div className={styles.inputForm}>
        <div className={styles.inputWrapper}>
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={handleInput}
            placeholder={placeholder}
            className={styles.inputField}
            disabled={disabled}
            onKeyDown={handleKeyDown}
            onCompositionStart={() => setIsComposing(true)}
            onCompositionEnd={() => setIsComposing(false)}
            enterKeyHint="send"
            autoComplete="off"
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            data-gramm="false"
            contentEditable="true"
            suppressContentEditableWarning={true}
          />
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

import { useState, useEffect } from 'react';
import { message } from 'antd';
import { Input } from '@chatui/core';
import {
  INTERACTION_TYPE,
  INTERACTION_OUTPUT_TYPE,
} from 'constants/courseConstants.js';

import styles from './ChatInputText.module.scss';
import { memo } from 'react';

const OUTPUT_TYPE_MAP = {
  [INTERACTION_TYPE.INPUT]: INTERACTION_OUTPUT_TYPE.TEXT,
  [INTERACTION_TYPE.PHONE]: INTERACTION_OUTPUT_TYPE.PHONE,
  [INTERACTION_TYPE.CHECKCODE]: INTERACTION_OUTPUT_TYPE.CHECKCODE,
};

export const ChatInputText = ({ onClick, type, disabled = false }) => {
  const [input, setInput] = useState('');
  const [messageApi, contextHolder] = message.useMessage();

  const outputType = OUTPUT_TYPE_MAP[type];

  const onSendClick = async () => {
    if (input.trim() === '') {
      messageApi.warning('请输入内容');
      return;
    }

    onClick?.(outputType, input.trim());
    setInput('');
  };

  useEffect(() => {
    if (!disabled) {
      const elem = document.querySelector(`.${styles.inputField}`)

      if (elem) {
        elem.focus();
      }
    }
  });

  return (
    <div className={styles.inputTextWrapper}>
      <div className={styles.inputForm}>
        <div className={styles.inputWrapper}>
          <Input
            autoSize
            type="text"
            value={input}
            onChange={(v) => setInput(v)}
            placeholder="请输入"
            className={styles.inputField}
            disabled={disabled}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                onSendClick();
              }
            }}
          >
          </Input>
          <img src={require('@Assets/newchat/light/icon-send.png')} alt="" className={styles.sendIcon} onClick={onSendClick} />
        </div>
        {contextHolder}
      </div>
    </div>
  );
};

export default memo(ChatInputText);

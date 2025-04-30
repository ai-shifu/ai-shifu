import styles from './ChatInputSmsCode.module.scss';
import { useState } from 'react';
import { message } from 'antd';
import { Input } from '@chatui/core';
import SubButton from 'Components/SubButton';
import { INTERACTION_OUTPUT_TYPE } from '@constants/courseContants';

export const ChatInputSmsCode = ({ onClick, type, props }) => {
  const [input, setInput] = useState('');
  const [messageApi, contextHolder] = message.useMessage();

  const onSendClick = async () => {
    const inputData = input.trim();
    if (inputData === '' || !/^\d{4}$/.test(inputData)) {
      messageApi.warning('请输入4位短信验证码');
      return;
    }

    onClick?.(INTERACTION_OUTPUT_TYPE.CHECKCODE, true, inputData);
    setInput('');
  };

  return (
    <div styles={styles.ChatInputSmsCode}>
      <div className={styles.inputForm}>
        <div className={styles.inputWrapper}>
          <Input
            maxLength={4}
            type="text"
            value={input}
            onChange={(v) => setInput(v)}
            placeholder=""
            className={styles.inputField}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                onSendClick();
              }
            }}
          />
        </div>
        <SubButton
          onClick={onSendClick}
          width={100}
          height={32}
          style={{ marginLeft: '15px' }}
        >
          提交
        </SubButton>
        {contextHolder}
      </div>
    </div>
  );
};

export default ChatInputSmsCode;

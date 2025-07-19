import styles from './ChatInputSmsCode.module.scss';

import { useState } from 'react';

// import { Input } from '@ai-shifu/chatui';
import { Input } from '../ForkChatUI/components/Input'
import SubButton from '@/c-components/SubButton';
import { INTERACTION_OUTPUT_TYPE } from '@/c-constants/courseConstants';

import { toast } from '@/hooks/use-toast';

export const ChatInputSmsCode = ({ onClick }) => {
  const [input, setInput] = useState('');

  const onSendClick = async () => {
    const inputData = input.trim();
    if (inputData === '' || !/^\d{4}$/.test(inputData)) {
      toast({
        title: '请输入4位短信验证码',
        variant: 'destructive'
      })
      return
    }

    onClick?.(INTERACTION_OUTPUT_TYPE.CHECKCODE, true, inputData);
    setInput('');
  }

  return (
    // @ts-expect-error EXPECT
  <div styles={styles.ChatInputSmsCode}>
      <div className={styles.inputForm}>
        <div className={styles.inputWrapper}>
          <Input
            maxLength={4}
            type="text"
            value={input}
            onChange={v => setInput(v)}
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
        {/* @ts-expect-error EXPECT */}
        <SubButton onClick={onSendClick} width={100} height={32} style={{ marginLeft: '15px' }} >
          提交
        </SubButton>
      </div>
  </div>);
}

export default ChatInputSmsCode;

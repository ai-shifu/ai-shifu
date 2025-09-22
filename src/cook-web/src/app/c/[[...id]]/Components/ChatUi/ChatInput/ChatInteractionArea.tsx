import React, { memo, useRef, useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import styles from './ChatInteractionArea.module.scss';
import {
  INTERACTION_TYPE,
  INTERACTION_DISPLAY_TYPE,
} from '@/c-constants/courseConstants';
import { getInteractionComponent } from './interactionRegistry';
import ChatInputText from './InputComponents/ChatInputText';
import AskButton from './InputComponents/AskButton';

// TODO: FIXME
// import all interaction components
// const importAll = (r) => r.keys().forEach(r);
// importAll(require.context('./InputComponents', true, /\.tsx$/));

export const ChatInteractionArea = ({
  type = INTERACTION_DISPLAY_TYPE.TEXT,
  props = {},
  onSend = () => {},
  disabled = false,
  askButtonState = { askMode: false, total: 1, used: 0 },
  onSizeChange = () => {},
}) => {
  const elemRef = useRef(null);
  const { t } = useTranslation();
  const [isInputVisible, setInputVisible] = useState(false);
  const [askContent, setAskContent] = useState('');

  // BUGFIX: 聊天输入框持久化存储优化
  // 问题：用户输入内容后刷新页面，输入框内容丢失，用户体验不佳
  // 解决：使用localStorage在父组件层面管理输入状态，确保页面刷新后内容保留
  // 架构：遵循React最佳实践，将状态提升到父组件，避免子组件直接操作localStorage

  // 创建localStorage的key，基于当前会话和输入类型
  const getStorageKey = () => {
    const pathname =
      typeof window !== 'undefined' ? window.location.pathname : '';
    return `chat_input_${pathname}_${type || 'default'}`;
  };

  // 从localStorage加载保存的输入值
  const getStoredValue = () => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(getStorageKey());
      return stored || '';
    }
    return '';
  };

  const [inputValue, setInputValue] = useState(() => getStoredValue());

  // 自动保存输入内容到localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
      if (inputValue.trim()) {
        localStorage.setItem(getStorageKey(), inputValue);
      } else {
        localStorage.removeItem(getStorageKey());
      }
    }
  }, [inputValue]);

  const onSendFunc = (type, display, val) => {
    if (disabled) {
      return;
    }
    setInputValue('');
    setAskContent('');
    // @ts-expect-error EXPECT
    onSend?.(type, display, val, props.scriptId);
  };

  const genRenderControl = () => {
    const Component = getInteractionComponent(type);
    if (Component) {
      return (
        <Component
          disabled={disabled}
          type={type}
          props={props}
          onClick={onSendFunc}
          initialValue={inputValue}
          onInputChange={setInputValue}
        />
      );
    }
    return <></>;
  };

  const resizeChange = useCallback(
    e => {
      // @ts-expect-error EXPECT
      onSizeChange?.({
        width: e.contentRect.width,
        height: e.contentRect.height,
      });
    },
    [onSizeChange],
  );

  const handleAskClick = () => {
    setInputVisible(!isInputVisible);
  };

  const onSendAsk = (type, display, val) => {
    setInputVisible(false);
    onSendFunc?.(INTERACTION_TYPE.ASK, true, val);
    setInputValue('');
    setAskContent('');
  };

  useEffect(() => {
    const resize = new ResizeObserver(e => {
      if (!Array.isArray(e) || !e.length) return;
      for (const ent of e) {
        resizeChange(ent);
      }
    });
    // @ts-expect-error EXPECT
    resize.observe(elemRef?.current);
    // Destroy the observer in a timely manner (important!!!)
    const curr = elemRef?.current;
    return () => {
      // @ts-expect-error EXPECT
      resize.unobserve(curr);
    };
  }, [resizeChange]);

  return (
    <div
      className={cn(styles.chatInputArea, disabled && styles.disabled)}
      ref={elemRef}
    >
      <div className={styles.controlContainer}>
        <div className={styles.controlWrapper}>
          <div className={styles.controlWrapperInner}>
            {!isInputVisible && genRenderControl()}{' '}
            {/* Display input box based on state */}
            {isInputVisible && (
              <ChatInputText
                id='askInput'
                onClick={onSendAsk}
                type='text'
                // @ts-expect-error EXPECT
                props={{ content: t('chat.askContent') }}
                visible={isInputVisible}
                initialValue={askContent}
                onInputChange={setAskContent}
              />
            )}
          </div>
          {/* @ts-expect-error EXPECT */}
          {askButtonState.visible && (
            <AskButton
              className={styles.askButton}
              disabled={!askButtonState.askMode}
              total={askButtonState.total}
              used={askButtonState.used}
              onClick={handleAskClick}
            />
          )}
        </div>
      </div>
      <div className={styles.tipText}>{t('chat.chatTips')}</div>
    </div>
  );
};

export default memo(ChatInteractionArea);

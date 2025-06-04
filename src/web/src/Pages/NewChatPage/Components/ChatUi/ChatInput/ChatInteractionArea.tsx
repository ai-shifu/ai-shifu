import React, { memo, useRef, useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import classNames from 'classnames';
import styles from './ChatInteractionArea.module.scss';
import {
  INTERACTION_TYPE,
  INTERACTION_DISPLAY_TYPE,
} from 'constants/courseConstants';
import { getInteractionComponent } from './interactionRegistry';
import ChatInputText from './InputComponents/ChatInputText';
import AskButton from './InputComponents/AskButton';

// import all interaction components
const importAll = (r) => r.keys().forEach(r);
importAll(require.context('./InputComponents', true, /\.tsx$/));

export const ChatInteractionArea = ({
  type = INTERACTION_DISPLAY_TYPE.TEXT,
  props = {},
  onSend = (type, display, val, scriptId) => {},
  disabled = false,
  askButtonState = { askMode: false, total: 1, used: 0 },
  onSizeChange = ({ width, height }) => {},
}) => {
  const elemRef = useRef();
  const { t } = useTranslation();
  const [isInputVisible, setInputVisible] = useState(false);
  const [askContent, setAskContent] = useState('');
  const [inputValue, setInputValue] = useState('');

  const onSendFunc = (type, display, val) => {
    if (disabled) {
      return;
    }
    setInputValue('');
    setAskContent('');
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
    (e) => {
      onSizeChange?.({
        width: e.contentRect.width,
        height: e.contentRect.height,
      });
    },
    [onSizeChange]
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
    const resize = new ResizeObserver((e) => {
      if (!Array.isArray(e) || !e.length) return;
      for (const ent of e) {
        resizeChange(ent);
      }
    });
    resize.observe(elemRef?.current);
    // Destroy the observer in a timely manner (important!!!)
    const curr = elemRef?.current;
    return () => {
      resize.unobserve(curr);
    };
  }, [resizeChange]);

  return (
    <div
      className={classNames(styles.chatInputArea, disabled && styles.disabled)}
      ref={elemRef}
    >
      <div className={styles.controlContainer}>
        <div className={styles.controlWrapper}>
          <div className={styles.controlWrapperInner}>
            {!isInputVisible && genRenderControl()}{' '}
            {/* Display input box based on state */}
            {isInputVisible && (
              <ChatInputText
                id="askInput"
                onClick={onSendAsk}
                type="text"
                props={{ content: t('chat.askContent') }}
                visible={isInputVisible}
                initialValue={askContent}
                onInputChange={setAskContent}
              />
            )}
          </div>
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

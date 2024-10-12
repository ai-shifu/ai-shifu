import styles from './ChatInteractionArea.module.scss';
import ChatInputText from './ChatInputText.jsx';
import ChatButtonGroup from './ChatButtonGroup.jsx';
import ChatInputButton from './ChatInputButton.jsx';
import { useTranslation } from 'react-i18next';
import { Button } from 'antd';

import {
  INTERACTION_TYPE,
  INTERACTION_DISPLAY_TYPE,
} from 'constants/courseConstants.js';
import classNames from 'classnames';
import { memo, useRef, useEffect } from 'react';
import { useCallback } from 'react';
import React, { useState } from 'react';
import { ConfigProvider } from 'antd';
import askIcon from '@Assets/newchat/light/svg-ask-16.svg';

const INTERACTION_DISPLAY_MAP = {
  [INTERACTION_TYPE.CONTINUE]: INTERACTION_DISPLAY_TYPE.BUTTON,
  [INTERACTION_TYPE.INPUT]: INTERACTION_DISPLAY_TYPE.TEXT,
  [INTERACTION_TYPE.BUTTONS]: INTERACTION_DISPLAY_TYPE.BUTTONS,
  [INTERACTION_TYPE.NEXT_CHAPTER]: INTERACTION_DISPLAY_TYPE.BUTTON,
  [INTERACTION_TYPE.PHONE]: INTERACTION_DISPLAY_TYPE.TEXT,
  [INTERACTION_TYPE.CHECKCODE]: INTERACTION_DISPLAY_TYPE.TEXT,
  [INTERACTION_TYPE.ORDER]: INTERACTION_DISPLAY_TYPE.BUTTON,
  [INTERACTION_TYPE.REQUIRE_LOGIN]: INTERACTION_DISPLAY_TYPE.BUTTON,

};

export const ChatInteractionArea = ({
  type = INTERACTION_DISPLAY_TYPE.TEXT,
  props = {},
  onSend = (type, val) => {},
  disabled = false,
  askMode = false,
  onSizeChange = ({ width, height }) => {},
}) => {

  console.log('ChatInteractionArea type', type);
  const displayType = INTERACTION_DISPLAY_MAP[type];
  const elemRef = useRef();
  const {t} = useTranslation();
  const [isInputVisible, setInputVisible] = useState(false);

  const onSendFunc = (type, val) => {
    if (disabled) {
      return;
    }
    console.log('onSendFunc type', type);
    onSend?.(type, val, props.scriptId);
  };

  const genRenderControl = () => {
    console.log('genRenderControl displayType', displayType);
    console.log('genRenderControl type', type);
    switch (displayType) {
      case INTERACTION_DISPLAY_TYPE.BUTTON:
        return (
          <ChatInputButton
            disabled={disabled}
            type={type}
            props={props}
            onClick={onSendFunc}
          />
        );
      case INTERACTION_DISPLAY_TYPE.TEXT:
        return (
          <ChatInputText
            disabled={disabled}
            type={type}
            props={props}
            onClick={onSendFunc}
          />
        );
      case INTERACTION_DISPLAY_TYPE.BUTTONS:
        return (
          <ChatButtonGroup
            disabled={disabled}
            type={type}
            props={props}
            onClick={onSendFunc}
          />
        );
      default:
        return <></>;
    }
  };

  const resizeChange = useCallback((e) => {
    onSizeChange?.({
      width: e.contentRect.width,
      height: e.contentRect.height,
    });
  }, [onSizeChange]);
  const handleAskClick = () => {
    setInputVisible(!isInputVisible);
  };

  const onSendAsk = (type, val) => {
    setInputVisible(false);
    onSendFunc?.(INTERACTION_TYPE.ASK, val);
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
          {(!isInputVisible) && genRenderControl()} {/* Display input box based on state */}
          {isInputVisible &&
            <ChatInputText
              id="askInput"
              onClick={onSendAsk}
              type="text"
              props={{ content: t('chat.askContent') }}
              visible={isInputVisible}
            />
          }
          <ConfigProvider
            theme={{
              components: {
                Button: {
                  colorPrimary: '#042ED2',
                  colorPrimaryHover: '#3658DB',
                  colorPrimaryActive: '#0325A8',
                  lineWidth: 0,
                },
              },
            }}
          >
            <Button type="primary" onClick={handleAskClick} className={styles.askButton} disabled={!askMode}>
              <div className={styles.askButtonContent}>
                <img src={askIcon} alt="" className={styles.askButtonIcon} />
                <span className={styles.askButtonText}>{t('chat.ask')}</span>
              </div>
            </Button>
          </ConfigProvider>
        </div>
      </div>
      <div className={styles.tipText}>
        {t('chat.chatTips')}
      </div>
    </div>
  );
};

export default memo(ChatInteractionArea);

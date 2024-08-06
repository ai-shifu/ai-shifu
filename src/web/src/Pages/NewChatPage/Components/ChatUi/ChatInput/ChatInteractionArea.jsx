/**
 * 聊天输入区域
 * 目前有三种类型的输入，下一步，文本，按钮组
 */
import styles from './ChatInteractionArea.module.scss';
import ChatInputText from './ChatInputText.jsx';
import ChatButtonGroup from './ChatButtonGroup.jsx';
import ChatInputButton from './ChatInputButton.jsx';
import { INTERACTION_TYPE, INTERACTION_DISPLAY_TYPE } from 'constants/courseConstants.js';
import classNames from 'classnames';
import { memo } from 'react';

const INTERACTION_DISPLAY_MAP = {
  [INTERACTION_TYPE.CONTINUE]: INTERACTION_DISPLAY_TYPE.BUTTON,
  [INTERACTION_TYPE.INPUT]: INTERACTION_DISPLAY_TYPE.TEXT,
  [INTERACTION_TYPE.BUTTONS]: INTERACTION_DISPLAY_TYPE.BUTTONS,
  [INTERACTION_TYPE.NEXT_CHAPTER]: INTERACTION_DISPLAY_TYPE.BUTTON,
  [INTERACTION_TYPE.PHONE]: INTERACTION_DISPLAY_TYPE.TEXT,
  [INTERACTION_TYPE.CHECKCODE]: INTERACTION_DISPLAY_TYPE.TEXT,
  [INTERACTION_TYPE.ORDER]: INTERACTION_DISPLAY_TYPE.BUTTON,
};

export const ChatInteractionArea = ({
  type = INTERACTION_DISPLAY_TYPE.TEXT,
  props = {},
  onSend = (type, val) => {},
  disabled = false,
}) => {
  const displayType = INTERACTION_DISPLAY_MAP[type];

  const onSendFunc = (type, val) => {
    if (disabled) {
      return;
    }
    onSend?.(type, val, props.scriptId);
  }

  const genRenderControl = () => {
    switch (displayType) {
      case INTERACTION_DISPLAY_TYPE.BUTTON:
        return <ChatInputButton
          disabled={disabled}
          type={type}
          props={props}
          onClick={onSendFunc}
        />
      case INTERACTION_DISPLAY_TYPE.TEXT:
        return <ChatInputText
          disabled={disabled}
          type={type}
          props={props}
          onClick={onSendFunc}
        />
      case INTERACTION_DISPLAY_TYPE.BUTTONS:
        return <ChatButtonGroup
          disabled={disabled}
          type={type}
          props={props}
          onClick={onSendFunc}
        />
      default:
        return <></>
    }
  }
  return (
    <div className={classNames(styles.chatInputArea, disabled && styles.disabled)}>
      {genRenderControl()}
      <div className={styles.tipText}>内容由 AI 大模型生成，无法确保真实准确，仅供学习参考</div>
    </div>
  );
};

export default memo(ChatInteractionArea);

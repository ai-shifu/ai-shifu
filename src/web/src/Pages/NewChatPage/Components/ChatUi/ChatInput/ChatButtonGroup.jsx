import MainButton from "Components/MainButton.jsx";
import styles from './ChatButtonGroup.module.scss';
import { INTERACTION_OUTPUT_TYPE } from 'constants/courseConstants.js';
import { memo } from "react";


/**
 * 聊天按钮组控件
 */
export const ChatButtonGroup = ({ type, props = [], onClick = (val) => {}, disabled = false }) => {
  const buttons = props.buttons;

  return (
    <div className={styles.buttonGroupWrapper}>
      <div className={styles.ChatButtonGroup}>
        {
          buttons.map((e, i) => {
            return <MainButton
              key={i}
              onClick={() => onClick?.(INTERACTION_OUTPUT_TYPE.SELECT, e.value)}
              style={{margin: '10px 0 0 10px'}}
              disabled={disabled}
            >{e.label}</MainButton>
          })
        }
      </div>
    </div>
  );
}

export default memo(ChatButtonGroup);

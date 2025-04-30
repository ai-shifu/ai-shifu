import MainButton from 'Components/MainButton';
import styles from './ChatButtonGroup.module.scss';
import { INTERACTION_OUTPUT_TYPE } from 'constants/courseConstants';
import { memo } from 'react';
import { registerInteractionType } from '../interactionRegistry';
import { INTERACTION_TYPE } from 'constants/courseConstants';

export const ChatButtonGroup = ({
  type,
  props = [],
  onClick = (val) => {},
  disabled = false,
}) => {
  const buttons = props.buttons;

  return (
    <div className={styles.buttonGroupWrapper}>
      <div className={styles.ChatButtonGroup}>
        {buttons.map((e, i) => {
          return (
            <MainButton
              key={i}
              onClick={() =>
                onClick?.(
                  INTERACTION_OUTPUT_TYPE.SELECT,
                  e.display !== undefined ? e.display : true,
                  e.value,
                )
              }
              disabled={disabled}
            >
              {e.label}
            </MainButton>
          );
        })}
      </div>
    </div>
  );
};

const ChatButtonGroupMemo = memo(ChatButtonGroup);
registerInteractionType(INTERACTION_TYPE.BUTTONS, ChatButtonGroupMemo);
export default ChatButtonGroupMemo;

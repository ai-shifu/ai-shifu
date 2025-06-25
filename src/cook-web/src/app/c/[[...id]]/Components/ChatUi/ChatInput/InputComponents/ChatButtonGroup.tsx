import styles from './ChatButtonGroup.module.scss';

import { memo } from "react";
import { Button } from '@/components/ui/button';

import { INTERACTION_OUTPUT_TYPE } from '@/c-constants/courseConstants';
import { registerInteractionType } from '../interactionRegistry';
import { INTERACTION_TYPE } from '@/c-constants/courseConstants';

export const ChatButtonGroup = ({ props = [], onClick, disabled = false }) => {
  // @ts-expect-error EXPECT
  const buttons = props.buttons;

  function handleBtnClick(btn) {
    const display = btn.display !== undefined ? true : btn.display;
    onClick?.(INTERACTION_OUTPUT_TYPE.SELECT,  display, btn.value)
  }

  return (
    <div className={styles.buttonGroupWrapper}>
      <div className={styles.ChatButtonGroup}>
        {
          buttons.map((el, i) => {
            const key = `${el.label}_${el.value}_${i}`
            return (
              <Button
                key={key}
                onClick={() => handleBtnClick(el)}
                disabled={disabled}>
                  {el.label}
              </Button>
            )
          })
        }
      </div>
    </div>
  );
}

const ChatButtonGroupMemo = memo(ChatButtonGroup);
registerInteractionType(INTERACTION_TYPE.BUTTONS, ChatButtonGroupMemo);
export default ChatButtonGroupMemo;

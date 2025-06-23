import { memo } from 'react';
import { shifu } from '@/c-service/Shifu';

const ActiveMessageControl = ({ msg, action, button, recordId }) => {
  const Control = shifu.getControl(shifu.ControlTypes.ACTIVE_MESSAGE);

  return Control ? (
    <>
      <Control msg={msg} action={action} button={button} recordId={recordId} />
    </>
  ) : (
    <></>
  );
};

export default memo(ActiveMessageControl);

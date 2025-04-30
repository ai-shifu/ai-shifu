import { memo } from 'react';
import { useShallow } from 'zustand/react/shallow';
import PayModal from 'Pages/NewChatPage/Components/Pay/PayModal';
import PayModalM from 'Pages/NewChatPage/Components/Pay/PayModalM';
import { customEvents, EVENT_TYPE } from 'ShiNiang/events/event';
import { useState } from 'react';
import { shifu } from 'ShiNiang/config/config';
import { usePayStore } from 'ShiNiang/stores/usePayStore';
const NonBlockPayControl = ({ payload, onComplete, onClose }) => {
  const [isShow, setIsShow] = useState(true);
  const { updateHasPay } = usePayStore(
    useShallow((state) => ({ updateHasPay: state.updateHasPay })),
  );

  const onPayModalOk = () => {
    updateHasPay(true);
    onComplete?.(payload.type, payload.val, payload.scriptId);
  };

  const onNonBlockPayModalClose = () => {
    customEvents.dispatchEvent(
      new CustomEvent(EVENT_TYPE.NON_BLOCK_PAY_MODAL_CLOSED, { detail: {} }),
    );
    onComplete?.(
      shifu.constants.INTERACTION_OUTPUT_TYPE.CONTINUE,
      payload.label,
      payload.scriptId,
    );
    onClose?.();
  };

  return (
    <>
      {isShow &&
        (shifu.getConfig().mobileStyle ? (
          <PayModalM
            open={isShow}
            onCancel={onNonBlockPayModalClose}
            onOk={onPayModalOk}
            type={''}
            payload={{}}
          />
        ) : (
          <PayModal
            open={isShow}
            onCancel={onNonBlockPayModalClose}
            onOk={onPayModalOk}
            type={''}
            payload={{}}
          />
        ))}
    </>
  );
};

export default memo(NonBlockPayControl);

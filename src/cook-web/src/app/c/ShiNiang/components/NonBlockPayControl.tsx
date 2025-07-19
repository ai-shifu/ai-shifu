import { memo, useState } from 'react';
import { useShallow } from 'zustand/react/shallow';

import PayModal from '@/app/c/[[...id]]/Components/Pay/PayModal';
import PayModalM from '@/app/c/[[...id]]/Components/Pay/PayModalM';
import { customEvents, EVENT_TYPE } from '../events/event';

import { shifu } from '../config/config';
import { usePayStore } from '../stores/usePayStore';
const NonBlockPayControl = ({ payload, onComplete, onClose }) => {
  const [isShow] = useState(true);
  const { updateHasPay } = usePayStore(
    useShallow((state) => ({ updateHasPay: state.updateHasPay }))
  );

  const onPayModalOk = () => {
    updateHasPay(true);
    onComplete?.(payload.type, payload.val, payload.scriptId);
  };

  const onNonBlockPayModalClose = () => {
    customEvents.dispatchEvent(
      new CustomEvent(EVENT_TYPE.NON_BLOCK_PAY_MODAL_CLOSED, { detail: {} })
    );
    // @ts-expect-error EXPECT
    onComplete?.(shifu.constants.INTERACTION_OUTPUT_TYPE.CONTINUE, payload.label, payload.scriptId);
    onClose?.();
  };

  return (
    <>
      {/* @ts-expect-error EXPECT */}
      {isShow && (shifu.getConfig().mobileStyle ? (
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

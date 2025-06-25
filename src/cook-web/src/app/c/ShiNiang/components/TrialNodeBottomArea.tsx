import { memo } from 'react';
import { useShallow } from 'zustand/react/shallow';
import styles from './TrialNodeBottomArea.module.scss';
import { shifu } from '../config/config';
import { usePayStore } from '../stores/usePayStore';
import ToPayButton from './ToPayButton';
import { useEffect } from 'react';
import { useCallback } from 'react';

const TrialNodeBottomArea = ({ payload }) => {
  const { hasPay, updateHasPay } = usePayStore(
    useShallow((state) => ({
      hasPay: state.hasPay,
      updateHasPay: state.updateHasPay,
    }))
  );

  // @ts-expect-error EXPECT
  const { trackEvent, EVENT_NAMES } = shifu.hooks.useTracking();

  const onClick = useCallback( () => {
    // @ts-expect-error EXPECT
    shifu.payTools.openPay({});
    trackEvent(EVENT_NAMES.POP_PAY, { from: 'left-nav-banner' });
  }, [EVENT_NAMES.POP_PAY, trackEvent]);

  useEffect(() => {
    const onModalOk = () => {
      updateHasPay(true);
    };
    // @ts-expect-error EXPECT
    shifu.events.addEventListener(shifu.EventTypes.PAY_MODAL_OK, onModalOk);
    
    return () => {
      // @ts-expect-error EXPECT
      shifu.events.removeEventListener(shifu.EventTypes.PAY_MODAL_OK, onModalOk);
    }
  });

  return hasPay ? (
    <></>
  ) : (
    <>
      <ToPayButton
        className={styles.trialNodeBottomArea}
        onClick={onClick}
        height="48px"
      >
        <div className={styles.buttonContent}>
          <div className={styles.row1}>{payload.banner_info}</div>
          <div className={styles.row2}>{payload.banner_title}</div>
        </div>
      </ToPayButton>
    </>
  );
};

export default memo(TrialNodeBottomArea);

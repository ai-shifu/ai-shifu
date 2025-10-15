import { memo } from 'react';
import { useShallow } from 'zustand/react/shallow';
import styles from './TrialNodeBottomArea.module.scss';
import { shifu } from '../config/config';
import { usePayStore } from '../stores/usePayStore';
import ToPayButton from './ToPayButton';
import { useEffect } from 'react';
import { useCallback } from 'react';
import { useCourseStore } from '@/c-store/useCourseStore';

const TrialNodeBottomArea = ({ payload }) => {
  const { hasPay, updateHasPay } = usePayStore(
    useShallow(state => ({
      hasPay: state.hasPay,
      updateHasPay: state.updateHasPay,
    })),
  );

  const { openPayModal, payModalResult } = useCourseStore(
    useShallow(state => ({
      openPayModal: state.openPayModal,
      payModalResult: state.payModalResult,
    })),
  );

  // @ts-expect-error EXPECT
  const { trackEvent, EVENT_NAMES } = shifu.hooks.useTracking();

  const onClick = useCallback(() => {
    openPayModal();
    trackEvent(EVENT_NAMES.POP_PAY, { from: 'left-nav-banner' });
  }, [EVENT_NAMES.POP_PAY, openPayModal, trackEvent]);

  useEffect(() => {
    if (payModalResult === 'ok') {
      updateHasPay(true);
    }
  }, [payModalResult, updateHasPay]);

  return hasPay ? (
    <></>
  ) : (
    <>
      <ToPayButton
        className={styles.trialNodeBottomArea}
        onClick={onClick}
        height='48px'
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

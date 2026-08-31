import { memo, useCallback } from 'react';
import { shifu } from '@/c-service/Shifu';
import styles from './TrialNodeOuter.module.scss';
import { useTranslation } from 'react-i18next';
import {
  TRAIL_NODE_POSITION,
  type TrialNodePosition,
} from './TrialNodeBottomArea';

type TrialNodeOuterProps = {
  nodePosition: TrialNodePosition;
  payload: unknown;
};

const TrialNodeOuter = ({ nodePosition, payload }: TrialNodeOuterProps) => {
  const { t } = useTranslation();
  const getTrialNodeAreaControl = useCallback(() => {
    const Control = shifu.getControl(shifu.ControlTypes.TRIAL_NODE_BOTTOM_AREA);

    return Control ? (
      <Control payload={payload} />
    ) : (
      <>{t('common.core.none')}</>
    );
  }, [payload, t]);

  const getClassName = useCallback(() => {
    let className = '';

    if (nodePosition === TRAIL_NODE_POSITION.STICK_TOP) {
      className = styles.stickTop;
    } else if (nodePosition === TRAIL_NODE_POSITION.STICK_BOTTOM) {
      className = styles.stickBottom;
    }

    return className;
  }, [nodePosition]);

  const getStyle = useCallback(() => {
    if (nodePosition === TRAIL_NODE_POSITION.STICK_TOP) {
      return {
        top: `0px`,
      };
    }

    if (nodePosition === TRAIL_NODE_POSITION.STICK_BOTTOM) {
      return {
        bottom: `0px`,
      };
    }
  }, [nodePosition]);

  return (
    <div
      className={`${styles.trialNodeOuter} ${getClassName()}`}
      style={getStyle()}
    >
      {getTrialNodeAreaControl()}
    </div>
  );
};

export default memo(TrialNodeOuter);

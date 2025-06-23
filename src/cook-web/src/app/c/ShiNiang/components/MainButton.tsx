import styles from './MainButton.module.scss';
import { forwardRef, memo } from 'react';

import clsx from 'clsx';
import { Button } from '@/components/ui/button';

export const MainButton = forwardRef((props, ref) => {
  const height = props.height || 40;
  const shape = props.shape || 'round';
  return (
    <Button
      ref={ref}
      {...props}
      type="primary"
      shape={shape}
      className={clsx(styles.mainButton, props.className)}
      style={{ width: props.width, height, ...props.style }}
    >
      {props.children}
    </Button>
  );
});

MainButton.displayName = 'MainButton';

export default memo(MainButton);

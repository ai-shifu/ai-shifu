import styles from './MainButton.module.scss';
import { forwardRef, memo } from 'react';

import clsx from 'clsx';
import { Button } from '@/components/ui/button';

export const MainButton = forwardRef((props, ref) => {
  // @ts-expect-error EXPECT
  const height = props.height || 40;
  // @ts-expect-error EXPECT
  const shape = props.shape || 'round';
  return (
    <Button
      // @ts-expect-error EXPECT
      ref={ref}
      {...props}
      shape={shape}
      // @ts-expect-error EXPECT
      className={clsx(styles.mainButton, props.className)}
      // @ts-expect-error EXPECT
      style={{ width: props.width, height, ...props.style }}>
      {/* @ts-expect-error EXPECT */}
      {props.children}
    </Button>
  );
});

MainButton.displayName = 'MainButton';

export default memo(MainButton);

import styles from './MainButton.module.scss';
import { forwardRef, memo, ReactNode } from 'react';

import clsx from 'clsx';
import { Button, ButtonProps } from '@/components/ui/button';

interface MainButtonProps extends Omit<ButtonProps, 'shape'> {
  height?: number;
  shape?: 'round' | 'square';
  width?: number | string;
  children?: ReactNode;
}

export const MainButton = forwardRef<HTMLButtonElement, MainButtonProps>((props, ref) => {
  const { height = 40, shape = 'round', width, className, style, children, ...rest } = props;

  return (
    <Button
      ref={ref}
      {...rest}
      shape={shape}
      className={clsx(styles.mainButton, className)}
      style={{ width, height, ...style }}>
      {children}
    </Button>
  );
});

MainButton.displayName = 'MainButton';

export default memo(MainButton);

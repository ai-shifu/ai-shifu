import styles from './ToPayButton.module.scss';

import { memo } from 'react';
import clsx from 'clsx';
import { Button } from '@/components/ui/button';

const ToPayButton = ({
  children,
  className = '',
  onClick,
  height = '26px',
}) => {
  return (
    <Button
      className={clsx(styles.toPayButton, className)}
      style={{ height }}
      onClick={onClick}
    >
      {children}
    </Button>
  )
};

export default memo(ToPayButton);

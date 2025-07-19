import React from 'react';
import clsx from 'clsx';

export type CardActionsProps = {
  className?: string;
  direction?: 'column' | 'row';
};

export const CardActions: React.FC<CardActionsProps> = (props) => {
  // @ts-expect-error EXPECT
  const { children, className, direction, ...other } = props;
  return (
    <div
      className={clsx('CardActions', className, direction && `CardActions--${direction}`)}
      {...other}
    >
      {children}
    </div>
  );
};

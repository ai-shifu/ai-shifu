import * as React from 'react';
import { cn } from '@/lib/utils'
import Image from 'next/image';

import { Button, ButtonProps } from '../Button';
import { Icon } from '../Icon';

export interface IconButtonProps extends ButtonProps {
  img?: string;
}

export const IconButton: React.FC<IconButtonProps> = (props) => {
  const { className, icon, img, ...other } = props;
  return (
    <Button className={cn('IconBtn', className)} {...other}>
      {icon && <Icon type={icon} />}
      {!icon && img && <Image src={img} alt="" />}
    </Button>
  );
};

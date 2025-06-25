import * as React from 'react';
import { cn } from '@/lib/utils'

import Image from 'next/image';
import { Flex } from '../Flex';

export type EmptyProps = {
  className?: string;
  type?: 'error' | 'default';
  image?: string;
  tip?: string;
  children?: React.ReactNode;
};

const IMAGE_EMPTY = '//gw.alicdn.com/tfs/TB1fnnLRkvoK1RjSZFDXXXY3pXa-300-250.svg';
const IMAGE_OOPS = '//gw.alicdn.com/tfs/TB1lRjJRbvpK1RjSZPiXXbmwXXa-300-250.svg';

export const Empty: React.FC<EmptyProps> = (props) => {
  const { className, type, image, tip = 'empty', children } = props;
  const imgUrl = image || (type === 'error' ? IMAGE_OOPS : IMAGE_EMPTY);

  return (
    <Flex className={cn('Empty', className)} direction="column" center>
      <Image className="Empty-img" src={imgUrl} alt={tip} />
      {tip && <p className="Empty-tip">{tip}</p>}
      {children}
    </Flex>
  );
};

import * as React from 'react';
import { cn } from '@/lib/utils'

import Image from 'next/image';

export type AvatarSize = 'sm' | 'md' | 'lg';
export type AvatarShape = 'circle' | 'square';

export interface AvatarProps {
  className?: string;
  src?: string;
  alt?: string;
  url?: string;
  size?: AvatarSize;
  shape?: AvatarShape;
}

export const Avatar: React.FC<AvatarProps> = (props) => {
  // @ts-expect-error EXPECT
  const { className, src, alt = 'Avatar', url, size = 'md', shape = 'circle', children } = props;
  
  let width = 36;
  let height = 36;
  if (size === 'sm') {
    width = 24;
    height = 24;
  } else if (size === 'lg') {
    width = 40;
    height = 40;
  }

  const Element = url ? 'a' : 'span';
  return (
    <Element
      className={cn('Avatar', `Avatar--${size}`, `Avatar--${shape}`, className)}
      href={url}>
      {src ? <Image src={src} width={width} height={height} alt={alt} /> : children}
    </Element>
  );
};

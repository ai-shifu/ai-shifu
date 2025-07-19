import * as React from 'react';
import { cn } from '@/lib/utils'
import Image from 'next/image';

export type MediaObjectProps = {
  className?: string;
  picUrl?: string;
  picAlt?: string;
  picSize?: 'sm' | 'md' | 'lg';
  title?: string;
  meta?: React.ReactNode;
};

export const MediaObject: React.FC<MediaObjectProps> = (props) => {
  const { className, picUrl, picSize, title, picAlt, meta } = props;
  return (
    <div className={cn('MediaObject', className)}>
      {picUrl && (
        <div className={cn('MediaObject-pic', picSize && `MediaObject-pic--${picSize}`)}>
          <Image src={picUrl} alt={picAlt || title || ''} />
        </div>
      )}
      <div className="MediaObject-info">
        <h3 className="MediaObject-title">{title}</h3>
        <div className="MediaObject-meta">{meta}</div>
      </div>
    </div>
  );
};

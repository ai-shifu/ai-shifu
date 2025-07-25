import React from 'react';
import { Button } from '../Button';
import { Icon } from '../Icon';

import Image from 'next/image';

export interface ToolbarItemProps {
  type: string;
  title: string;
  icon?: string;
  img?: string;
  render?: any; // FIXME
}

export interface ToolbarButtonProps {
  item: ToolbarItemProps;
  onClick: (item: ToolbarItemProps, event: React.MouseEvent) => void;
}

export const ToolbarButton: React.FC<ToolbarButtonProps> = props => {
  const { item, onClick } = props;
  const { type, icon, img, title } = item;

  return (
    <div
      className='Toolbar-item'
      data-type={type}
    >
      <Button
        className='Toolbar-btn'
        onClick={e => onClick(item, e)}
      >
        <span className='Toolbar-btnIcon'>
          {icon && <Icon type={icon} />}
          {img && (
            <Image
              className='Toolbar-img'
              src={img}
              alt=''
            />
          )}
        </span>
        <span className='Toolbar-btnText'>{title}</span>
      </Button>
    </div>
  );
};

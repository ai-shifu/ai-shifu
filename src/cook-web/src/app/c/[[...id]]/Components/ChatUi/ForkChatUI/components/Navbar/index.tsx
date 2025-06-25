import * as React from 'react';
import { cn } from '@/lib/utils'

import Image from 'next/image';

import { IconButton, IconButtonProps } from '../IconButton';

export type NavbarProps = {
  title: string;
  className?: string;
  logo?: string;
  leftContent?: IconButtonProps;
  rightContent?: IconButtonProps[];
};

export const Navbar: React.FC<NavbarProps> = (props) => {
  const { className, title, logo, leftContent, rightContent = [] } = props;
  return (
    <header className={cn('Navbar', className)}>
      <div className="Navbar-left">{leftContent && <IconButton size="lg" {...leftContent} />}</div>
      <div className="Navbar-main">
        {logo ? (
          <Image className="Navbar-logo" src={logo} alt={title} />
        ) : (
          <h2 className="Navbar-title">{title}</h2>
        )}
      </div>
      <div className="Navbar-right">
        {rightContent.map((item) => (
          <IconButton size="lg" {...item} key={item.icon} />
        ))}
      </div>
    </header>
  );
};

import React from 'react';

export interface BubbleProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'content'> {
  type?: string;
  content?: React.ReactNode;
}

export const Bubble = (props: BubbleProps) => {
  const { type = 'text', content, children, ...other } = props;
  return (
    <div className={`Bubble ${type}`} data-type={type} {...other}>
      {content && <article>{content}</article>}
      {children}
    </div>
  );
};

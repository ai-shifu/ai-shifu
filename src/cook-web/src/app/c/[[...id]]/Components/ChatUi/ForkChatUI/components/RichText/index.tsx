import React from 'react';
import clsx from 'clsx';
import DOMPurify from 'dompurify';
import './configDOMPurify';

export interface RichTextProps extends React.HTMLAttributes<HTMLDivElement> {
  content: string;
  className?: string;
  // @ts-expect-error EXPECT
  options?: DOMPurify.Config;
}

export const RichText = React.forwardRef<HTMLDivElement, RichTextProps>((props, ref) => {
  const { className, content, options = {}, ...other } = props;
  const html = {
    // @ts-expect-error EXPECT
    __html: DOMPurify.sanitize(content, options) as string,
  };

  return (
    <div
      className={clsx('RichText', className)}
      dangerouslySetInnerHTML={html}
      ref={ref}
      {...other}
    />
  );
});

RichText.displayName = 'RichText';

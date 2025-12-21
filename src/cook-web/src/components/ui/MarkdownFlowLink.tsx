import React from 'react';
import { cn } from '@/lib/utils';

interface MarkdownFlowLinkProps {
  prefix?: string;
  suffix?: string;
  linkText?: string;
  className?: string;
  linkClassName?: string;
  title?: string;
}

/**
 * A reusable component for displaying MarkdownFlow links with customizable prefix and suffix text
 * Link inherits text color from parent and only adds underline to indicate clickability
 */
export const MarkdownFlowLink: React.FC<MarkdownFlowLinkProps> = ({
  prefix = '',
  suffix = '',
  linkText = 'MarkdownFlow',
  className = '',
  linkClassName = '',
  title,
}) => {
  const defaultLinkClass = "underline hover:opacity-80 transition-opacity duration-200 cursor-pointer";
  
  return (
    <span className={cn('inline', className)} title={title}>
      {prefix && <span>{prefix}</span>}
      {prefix && ' '}
      <a
        href="https://markdownflow.ai/"
        target="_blank"
        rel="noopener noreferrer"
        className={cn(defaultLinkClass, linkClassName)}
      >
        {linkText}
      </a>
      {suffix && ' '}
      {suffix && <span>{suffix}</span>}
    </span>
  );
};

export default MarkdownFlowLink;
import React from 'react';
import { cn } from '@/lib/utils';

interface MarkdownFlowLinkProps {
  prefix?: string;
  suffix?: string;
  linkText?: string;
  className?: string;
  linkClassName?: string;
  title?: string;
  targetUrl?: string;
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
  targetUrl = 'https://markdownflow.ai/',
}) => {
  const defaultLinkClass =
    'underline hover:opacity-80 transition-opacity duration-200 cursor-pointer';

  // Build content parts array and filter out empty elements
  const contentParts: React.ReactNode[] = [
    prefix && <span key='prefix'>{prefix}</span>,
    linkText && (
      <a
        key='link'
        href={targetUrl}
        target='_blank'
        rel='noopener noreferrer'
        className={cn(defaultLinkClass, linkClassName)}
      >
        {linkText}
      </a>
    ),
    suffix && <span key='suffix'>{suffix}</span>,
  ].filter(Boolean);

  // Use reduce to join parts with proper spacing
  const renderedContent = contentParts.reduce<React.ReactNode[]>(
    (acc, current, index) => {
      if (index === 0) return [current];
      return acc.concat(' ', current);
    },
    [],
  );

  return (
    <span
      className={cn('inline', className)}
      title={title}
    >
      {renderedContent}
    </span>
  );
};

export default MarkdownFlowLink;

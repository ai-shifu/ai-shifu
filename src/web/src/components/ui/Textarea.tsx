'use client';

import * as React from 'react';

import { cn } from '@/lib/utils';

type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  minRows?: number;
  maxRows?: number;
};

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    {
      className,
      minRows,
      maxRows,
      onInput,
      rows,
      value,
      defaultValue,
      ...props
    },
    ref,
  ) => {
    const innerRef = React.useRef<HTMLTextAreaElement | null>(null);
    const shouldAutoResize =
      typeof maxRows === 'number' || typeof minRows === 'number';
    const resolvedMinRows = minRows ?? rows;

    const setRefs = React.useCallback(
      (node: HTMLTextAreaElement | null) => {
        innerRef.current = node;
        if (typeof ref === 'function') {
          ref(node);
        } else if (ref) {
          (ref as React.MutableRefObject<HTMLTextAreaElement | null>).current =
            node;
        }
      },
      [ref],
    );

    const resizeTextarea = React.useCallback(() => {
      if (!shouldAutoResize) {
        return;
      }
      const textarea = innerRef.current;
      if (!textarea || typeof window === 'undefined') {
        return;
      }

      textarea.style.height = 'auto';
      const computedStyle = window.getComputedStyle(textarea);
      const lineHeight = parseFloat(computedStyle.lineHeight || '0') || 20;
      const padding =
        parseFloat(computedStyle.paddingTop || '0') +
        parseFloat(computedStyle.paddingBottom || '0');
      const border =
        parseFloat(computedStyle.borderTopWidth || '0') +
        parseFloat(computedStyle.borderBottomWidth || '0');

      const minHeight = (resolvedMinRows ?? 1) * lineHeight + padding + border;
      const maxHeight =
        typeof maxRows === 'number'
          ? maxRows * lineHeight + padding + border
          : undefined;

      const nextHeight = Math.max(minHeight, textarea.scrollHeight);
      const appliedHeight = maxHeight
        ? Math.min(nextHeight, maxHeight)
        : nextHeight;

      textarea.style.height = `${appliedHeight}px`;
      if (maxHeight) {
        textarea.style.maxHeight = `${maxHeight}px`;
        textarea.style.overflowY = nextHeight > maxHeight ? 'auto' : 'hidden';
      } else {
        textarea.style.removeProperty('max-height');
        textarea.style.overflowY = 'hidden';
      }
    }, [maxRows, resolvedMinRows, shouldAutoResize]);

    React.useEffect(() => {
      resizeTextarea();
    }, [resizeTextarea, value, defaultValue]);

    const handleInput = (event: React.FormEvent<HTMLTextAreaElement>) => {
      if (shouldAutoResize) {
        resizeTextarea();
      }
      onInput?.(event);
    };

    return (
      <textarea
        className={cn(
          'break-words break-all flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50',
          className,
        )}
        rows={rows ?? resolvedMinRows}
        ref={setRefs}
        value={value}
        defaultValue={defaultValue}
        onInput={handleInput}
        {...props}
      />
    );
  },
);
Textarea.displayName = 'Textarea';

export { Textarea };

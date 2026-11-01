'use client';

import AdminTooltipText from '@/app/admin/components/AdminTooltipText';

type StackedTooltipTextProps = {
  primary: string;
  primaryEmptyValue: string;
  primaryClassName: string;
  secondary?: string;
  secondaryEmptyValue: string;
  secondaryClassName: string;
  /**
   * Wraps the secondary line in a muted text container. Some table cells
   * render the secondary tooltip directly, others inside a wrapper.
   */
  wrapSecondary?: boolean;
};

/**
 * Two-line table cell content: a prominent primary line and an optional
 * muted secondary line, both truncated with a tooltip.
 */
export default function StackedTooltipText({
  primary,
  primaryEmptyValue,
  primaryClassName,
  secondary,
  secondaryEmptyValue,
  secondaryClassName,
  wrapSecondary = false,
}: StackedTooltipTextProps) {
  const secondaryText = secondary ? (
    <AdminTooltipText
      text={secondary}
      emptyValue={secondaryEmptyValue}
      className={secondaryClassName}
    />
  ) : null;

  return (
    <div className='flex flex-col gap-0.5 leading-tight'>
      <div className='font-medium text-foreground'>
        <AdminTooltipText
          text={primary}
          emptyValue={primaryEmptyValue}
          className={primaryClassName}
        />
      </div>
      {secondaryText && wrapSecondary ? (
        <div className='text-xs text-muted-foreground'>{secondaryText}</div>
      ) : (
        secondaryText
      )}
    </div>
  );
}

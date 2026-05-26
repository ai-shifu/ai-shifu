'use client';

import type { ComponentPropsWithoutRef, ReactNode } from 'react';
import { cn } from '@/lib/utils';

export const ADMIN_TITLE_HEADING_CLASSNAME =
  'text-[var(--heading-md-font-size,30px)]';

export const ADMIN_TITLE_HEADLINE_TABS_LIST_CLASSNAME =
  '!inline-flex !h-auto !items-end !justify-start !gap-10 !rounded-none !bg-transparent !p-0';

export const ADMIN_TITLE_HEADLINE_TABS_TRIGGER_CLASSNAME =
  "!relative !h-auto !rounded-none !bg-transparent !px-0 !pb-4 !pt-0 text-[var(--heading-md-font-size,30px)] [font-style:normal] font-[var(--heading-md-font-weight,700)] leading-[var(--heading-md-line-height,36px)] tracking-[var(--heading-md-letter-spacing,0)] !text-[var(--base-foreground,#0A0A0A)] !shadow-none transition-colors focus-visible:!outline-none focus-visible:!ring-0 data-[state=active]:!bg-transparent data-[state=active]:!text-[var(--base-foreground,#0A0A0A)] data-[state=active]:!shadow-none after:pointer-events-none after:absolute after:bottom-0 after:left-0 after:h-1 after:w-full after:origin-left after:scale-x-0 after:bg-black after:transition-transform after:content-[''] data-[state=active]:after:scale-x-100";

const ADMIN_TITLE_HEADING_STYLE = {
  color: 'var(--base-foreground, #0A0A0A)',
  fontSize: 'var(--heading-md-font-size, 30px)',
  fontStyle: 'normal',
  fontWeight: 'var(--heading-md-font-weight, 700)',
  lineHeight: 'var(--heading-md-line-height, 36px)',
  letterSpacing: 'var(--heading-md-letter-spacing, 0)',
} as const;

export const ADMIN_TITLE_HEADLINE_TABS_TRIGGER_STYLE =
  ADMIN_TITLE_HEADING_STYLE;

type AdminTitleProps = ComponentPropsWithoutRef<'div'> & {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  tabs?: ReactNode;
  contentClassName?: string;
  titleClassName?: string;
  descriptionClassName?: string;
  actionsClassName?: string;
  tabsClassName?: string;
};

export default function AdminTitle({
  title,
  description,
  actions,
  tabs,
  className,
  contentClassName,
  titleClassName,
  descriptionClassName,
  actionsClassName,
  tabsClassName,
  ...props
}: AdminTitleProps) {
  const hasHeaderContent = Boolean(title || description || actions);

  return (
    <div
      className={cn('shrink-0', className)}
      {...props}
    >
      <div className={cn('py-6 pl-0 pr-0', contentClassName)}>
        {hasHeaderContent ? (
          <div className='flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between'>
            <div className='min-w-0 space-y-1'>
              {title ? (
                <h1
                  className={cn(ADMIN_TITLE_HEADING_CLASSNAME, titleClassName)}
                  style={ADMIN_TITLE_HEADING_STYLE}
                >
                  {title}
                </h1>
              ) : null}
              {description ? (
                <p
                  className={cn(
                    'text-sm text-muted-foreground',
                    descriptionClassName,
                  )}
                >
                  {description}
                </p>
              ) : null}
            </div>
            {actions ? (
              <div className={cn('w-full lg:w-auto', actionsClassName)}>
                {actions}
              </div>
            ) : null}
          </div>
        ) : null}
        {tabs ? (
          <div className={cn(hasHeaderContent ? 'mt-5' : '', tabsClassName)}>
            {tabs}
          </div>
        ) : null}
      </div>
    </div>
  );
}

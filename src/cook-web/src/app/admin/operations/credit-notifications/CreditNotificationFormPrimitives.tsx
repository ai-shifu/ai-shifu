import React from 'react';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import { Label } from '@/components/ui/Label';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export function CreditNotificationFormField({
  label,
  htmlFor,
  description,
  tooltip,
  children,
}: {
  label: React.ReactNode;
  htmlFor?: string;
  description?: React.ReactNode;
  tooltip?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className='flex items-center gap-1.5'>
        <Label
          htmlFor={htmlFor}
          className='text-xs font-medium text-muted-foreground'
        >
          {label}
        </Label>
        {tooltip ? (
          <CreditNotificationHelpTooltip>
            {tooltip}
          </CreditNotificationHelpTooltip>
        ) : null}
      </div>
      <div className='mt-1'>{children}</div>
      {description ? (
        <p className='mt-1 text-[11px] leading-4 text-muted-foreground'>
          {description}
        </p>
      ) : null}
    </div>
  );
}

export function CreditNotificationConfigSection({
  title,
  description,
  children,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className='rounded-xl border border-border bg-white p-4 shadow-sm'>
      <div>
        <h2 className='text-sm font-semibold text-foreground'>{title}</h2>
        {description ? (
          <p className='mt-1 text-xs text-muted-foreground'>{description}</p>
        ) : null}
      </div>
      <div className='mt-4 space-y-4'>{children}</div>
    </section>
  );
}

export function CreditNotificationHelpTooltip({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <TooltipProvider delayDuration={0}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type='button'
            className='inline-flex h-4 w-4 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2'
            aria-label={typeof children === 'string' ? children : undefined}
          >
            <QuestionMarkCircleIcon className='h-4 w-4' />
          </button>
        </TooltipTrigger>
        <TooltipContent className='max-w-64 text-left text-xs leading-5'>
          {children}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

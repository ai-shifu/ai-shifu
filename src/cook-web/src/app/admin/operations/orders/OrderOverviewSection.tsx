'use client';

import React from 'react';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import { X } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

type OrderOverviewCard = {
  key: string;
  label: string;
  value: string;
  tooltip: string;
  onClick?: () => void;
};

type OrderOverviewSectionProps = {
  title: string;
  cards: OrderOverviewCard[];
  activeCardLabel?: string | null;
  activeFilterLabel: string;
  clearLabel: string;
  staleMessage?: string | null;
  onClearActive?: () => void;
  gridClassName?: string;
};

export default function OrderOverviewSection({
  title,
  cards,
  activeCardLabel,
  activeFilterLabel,
  clearLabel,
  staleMessage,
  onClearActive,
  gridClassName,
}: OrderOverviewSectionProps) {
  return (
    <div className='mb-5 rounded-xl border border-border bg-white p-4 shadow-sm'>
      <div className='mb-3'>
        <h2 className='text-base font-semibold text-foreground'>{title}</h2>
      </div>

      {staleMessage ? (
        <div className='mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800'>
          {staleMessage}
        </div>
      ) : null}

      <div
        className={cn(
          'grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4 min-[1680px]:grid-cols-6',
          gridClassName,
        )}
      >
        {cards.map(card => {
          const content = (
            <>
              <div className='text-sm text-muted-foreground'>{card.label}</div>
              <div className='mt-3 text-2xl font-semibold text-foreground transition-colors group-hover:text-primary'>
                {card.value}
              </div>
            </>
          );

          return (
            <div
              key={card.key}
              className='rounded-lg border border-border/70 bg-muted/20 p-4 transition-colors hover:border-primary/30 hover:bg-primary/[0.04]'
            >
              <div className='flex items-start justify-between gap-2'>
                {card.onClick ? (
                  <button
                    type='button'
                    className='group min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2'
                    onClick={card.onClick}
                  >
                    {content}
                  </button>
                ) : (
                  <div className='min-w-0 flex-1'>{content}</div>
                )}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type='button'
                      aria-label={card.tooltip}
                      className='inline-flex h-4 w-4 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2'
                    >
                      <QuestionMarkCircleIcon className='h-4 w-4' />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent className='max-w-56 text-left leading-5'>
                    {card.tooltip}
                  </TooltipContent>
                </Tooltip>
              </div>
            </div>
          );
        })}
      </div>

      {activeCardLabel && onClearActive ? (
        <div className='mt-4 flex flex-wrap items-center gap-2'>
          <span className='text-sm text-muted-foreground'>
            {activeFilterLabel}
          </span>
          <button
            type='button'
            aria-label={`${activeCardLabel} ${clearLabel}`}
            className='inline-flex items-center gap-1 rounded-full border border-border bg-muted/30 px-3 py-1 text-sm text-foreground transition-colors hover:bg-muted'
            onClick={onClearActive}
          >
            <span>{activeCardLabel}</span>
            <X className='h-3.5 w-3.5' />
          </button>
        </div>
      ) : null}
    </div>
  );
}

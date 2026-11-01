'use client';

import { Card, CardContent } from '@/components/ui/Card';
import { cn } from '@/lib/utils';
import { splitTimestampValue } from './course-feedback-display';

export type CourseFeedbackSummaryCard = {
  key: string;
  label: string;
  value: string;
  tone: 'value' | 'timestamp';
};

type CourseFeedbackSummaryCardsProps = {
  cards: CourseFeedbackSummaryCard[];
  gridClassName: string;
  /**
   * `compact` is used by the teacher dashboard, `comfortable` by the
   * operator admin pages.
   */
  size: 'compact' | 'comfortable';
};

const SIZE_CLASSES = {
  compact: {
    value: 'text-xl',
    timestampDate: 'text-base font-medium',
    timestampTime: 'text-sm',
  },
  comfortable: {
    value: 'text-2xl',
    timestampDate: 'text-lg font-medium',
    timestampTime: 'text-base',
  },
} as const;

export default function CourseFeedbackSummaryCards({
  cards,
  gridClassName,
  size,
}: CourseFeedbackSummaryCardsProps) {
  const sizeClasses = SIZE_CLASSES[size];

  return (
    <div className={gridClassName}>
      {cards.map(card => (
        <Card
          key={card.key}
          className='border-border/80 shadow-sm'
        >
          <CardContent className='flex h-full flex-col p-4'>
            <div className='text-sm font-medium text-muted-foreground'>
              {card.label}
            </div>
            {card.tone === 'timestamp' ? (
              <div className='mt-3 space-y-0.5 text-foreground'>
                {splitTimestampValue(card.value).map((part, index) => (
                  <div
                    key={`${card.key}-${part}-${index}`}
                    className={cn(
                      'break-all tracking-tight',
                      index === 0
                        ? sizeClasses.timestampDate
                        : sizeClasses.timestampTime,
                    )}
                  >
                    {part}
                  </div>
                ))}
              </div>
            ) : (
              <div
                className={cn(
                  'mt-3 font-semibold text-foreground',
                  sizeClasses.value,
                )}
              >
                {card.value}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

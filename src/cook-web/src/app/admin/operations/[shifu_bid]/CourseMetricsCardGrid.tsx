'use client';

import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';

type MetricCard = {
  label: string;
  value: string;
  onClick?: () => void;
  actionLabel?: string;
};

type CourseMetricsCardGridProps = {
  title: string;
  cards: MetricCard[];
};

export default function CourseMetricsCardGrid({
  title,
  cards,
}: CourseMetricsCardGridProps) {
  return (
    <Card>
      <CardHeader className='pb-4'>
        <CardTitle className='text-base font-semibold tracking-normal'>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-5'>
          {cards.map(card => {
            const cardContent = (
              <>
                <div className='text-sm font-medium text-muted-foreground'>
                  {card.label}
                </div>
                <div className='mt-3 flex items-end gap-1.5'>
                  <span
                    className={cn(
                      'text-2xl font-semibold',
                      card.onClick ? 'text-primary' : 'text-foreground',
                    )}
                  >
                    {card.value}
                  </span>
                </div>
              </>
            );

            if (card.onClick) {
              return (
                <button
                  key={card.label}
                  type='button'
                  aria-label={card.actionLabel || card.label}
                  className='rounded-lg border border-border/70 bg-muted/20 p-4 text-left transition-colors hover:border-primary/30 hover:bg-primary/[0.04]'
                  onClick={card.onClick}
                >
                  {cardContent}
                </button>
              );
            }

            return (
              <div
                key={card.label}
                className='rounded-lg border border-border/70 bg-muted/20 p-4 text-left'
              >
                {cardContent}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

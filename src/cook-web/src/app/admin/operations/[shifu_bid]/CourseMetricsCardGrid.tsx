'use client';

import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
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
  gridClassName?: string;
};

const splitTrailingParenthetical = (label: string) => {
  const matched = label.match(/^(.*?)(\s*\([^()]+\))$/);
  if (!matched) {
    return null;
  }
  const mainText = matched[1]?.trim() || '';
  const suffixText = matched[2]?.trim() || '';
  if (!mainText || !suffixText) {
    return null;
  }
  return {
    mainText,
    suffixText,
  };
};

export default function CourseMetricsCardGrid({
  title,
  cards,
  gridClassName,
}: CourseMetricsCardGridProps) {
  const emptyValue = '--';

  return (
    <Card>
      <CardHeader className='pb-4'>
        <CardTitle className='text-base font-semibold tracking-normal'>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div
          className={cn(
            'grid gap-3 sm:grid-cols-2 xl:grid-cols-5',
            gridClassName,
          )}
        >
          {cards.map(card => {
            const labelParts = splitTrailingParenthetical(card.label);
            const cardContent = (
              <>
                <div className='min-h-12 text-sm font-medium leading-6 text-muted-foreground'>
                  <AdminTooltipText
                    text={card.label}
                    emptyValue={emptyValue}
                    displayText={
                      labelParts ? (
                        <>
                          <span className='break-words'>
                            {labelParts.mainText}
                          </span>{' '}
                          <span className='inline-block whitespace-nowrap'>
                            {labelParts.suffixText}
                          </span>
                        </>
                      ) : undefined
                    }
                    className='line-clamp-2 whitespace-normal break-words'
                  />
                </div>
                <div className='mt-3 flex items-end gap-1.5'>
                  <span
                    className={cn(
                      'text-2xl font-semibold transition-colors',
                      card.onClick
                        ? 'text-foreground group-hover:text-primary'
                        : 'text-foreground',
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
                  className='group cursor-pointer rounded-lg border border-border/70 bg-muted/20 p-4 text-left transition-colors hover:border-primary/30 hover:bg-primary/[0.04]'
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

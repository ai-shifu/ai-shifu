'use client';

import AdminCountCard from '@/app/admin/components/AdminCountCard';
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
            const cardTitle = (
              <AdminTooltipText
                text={card.label}
                emptyValue={emptyValue}
                displayText={
                  labelParts ? (
                    <>
                      <span className='break-words'>{labelParts.mainText}</span>{' '}
                      <span className='inline-block whitespace-nowrap'>
                        {labelParts.suffixText}
                      </span>
                    </>
                  ) : undefined
                }
                className='line-clamp-2 whitespace-normal break-words'
              />
            );

            if (card.onClick) {
              return (
                <button
                  key={card.label}
                  type='button'
                  aria-label={card.actionLabel || card.label}
                  className='group cursor-pointer text-left transition-colors'
                  onClick={card.onClick}
                >
                  <AdminCountCard
                    title={cardTitle}
                    value={card.value}
                    className='h-full transition-colors group-hover:border-primary/30'
                    valueClassName='transition-colors group-hover:text-primary'
                  />
                </button>
              );
            }

            return (
              <AdminCountCard
                key={card.label}
                title={cardTitle}
                value={card.value}
                className='h-full text-left'
              />
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

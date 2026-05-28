import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  type CourseQuickFilterKey,
  formatCount,
} from './operationCoursePageShared';

export type CourseOverviewCard = {
  key: string;
  label: string;
  value: number;
  tooltip: string;
  quickFilterKey: CourseQuickFilterKey;
};

type CourseOverviewSectionProps = {
  title: string;
  cards: CourseOverviewCard[];
  locale: string;
  onQuickFilter: (quickFilter: CourseQuickFilterKey) => void;
};

export default function CourseOverviewSection({
  title,
  cards,
  locale,
  onQuickFilter,
}: CourseOverviewSectionProps) {
  return (
    <div className='mb-5 rounded-xl border border-border bg-white p-4 shadow-sm'>
      <div className='mb-3'>
        <h2 className='text-base font-semibold text-foreground'>{title}</h2>
      </div>
      <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-3 min-[1680px]:grid-cols-6'>
        {cards.map(card => (
          <div
            key={card.key}
            className='rounded-lg border border-border/70 bg-muted/20 p-4'
          >
            <div className='flex items-start justify-between gap-2'>
              <button
                type='button'
                aria-label={card.label}
                className='group -m-2 min-w-0 flex-1 rounded-md border border-transparent p-2 text-left transition-colors hover:border-primary/30 hover:bg-primary/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2'
                onClick={() => onQuickFilter(card.quickFilterKey)}
              >
                <div className='text-sm text-muted-foreground'>
                  {card.label}
                </div>
                <div className='mt-3 text-2xl font-semibold text-foreground transition-colors group-hover:text-primary'>
                  {formatCount(card.value, locale)}
                </div>
              </button>
              <TooltipProvider delayDuration={0}>
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
              </TooltipProvider>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

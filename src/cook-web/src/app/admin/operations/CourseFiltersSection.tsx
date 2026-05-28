import { X } from 'lucide-react';
import AdminFilter, {
  type AdminFilterItem,
} from '@/app/admin/components/AdminFilter';
import type { CourseOverviewCard } from './CourseOverviewSection';
import type { CourseQuickFilterKey } from './operationCoursePageShared';

type CourseFiltersSectionProps = {
  items: AdminFilterItem[];
  expanded: boolean;
  activeQuickFilterCard: CourseOverviewCard | null;
  clearLabel: string;
  activeFilterLabel: string;
  resetLabel: string;
  searchLabel: string;
  expandLabel: string;
  collapseLabel: string;
  onExpandedChange: (expanded: boolean) => void;
  onReset: () => void;
  onSearch: () => void;
  onQuickFilter: (quickFilter: CourseQuickFilterKey) => void;
};

export default function CourseFiltersSection({
  items,
  expanded,
  activeQuickFilterCard,
  clearLabel,
  activeFilterLabel,
  resetLabel,
  searchLabel,
  expandLabel,
  collapseLabel,
  onExpandedChange,
  onReset,
  onSearch,
  onQuickFilter,
}: CourseFiltersSectionProps) {
  return (
    <div
      className='rounded-xl border border-border bg-white p-4 mb-5 shadow-sm transition-all'
      data-testid='admin-operations-filters'
    >
      <div className='space-y-4'>
        {activeQuickFilterCard ? (
          <div className='flex flex-wrap items-center gap-2'>
            <span className='text-sm text-muted-foreground'>
              {activeFilterLabel}
            </span>
            <button
              type='button'
              aria-label={`${activeQuickFilterCard.label} ${clearLabel}`}
              className='inline-flex items-center gap-1 rounded-full border border-border bg-muted/30 px-3 py-1 text-sm text-foreground transition-colors hover:bg-muted'
              onClick={() => onQuickFilter('')}
            >
              <span>{activeQuickFilterCard.label}</span>
              <X className='h-3.5 w-3.5' />
            </button>
          </div>
        ) : null}
        <AdminFilter
          items={items}
          expanded={expanded}
          onExpandedChange={onExpandedChange}
          onReset={onReset}
          onSearch={onSearch}
          resetLabel={resetLabel}
          searchLabel={searchLabel}
          expandLabel={expandLabel}
          collapseLabel={collapseLabel}
          collapsedCount={2}
          className='bg-transparent'
          contentClassName='min-w-0'
          labelClassName='w-20 text-right'
          collapsedGridClassName='gap-x-5 xl:grid-cols-3'
          expandedGridClassName='gap-x-5 xl:grid-cols-3'
          labelColon
        />
      </div>
    </div>
  );
}

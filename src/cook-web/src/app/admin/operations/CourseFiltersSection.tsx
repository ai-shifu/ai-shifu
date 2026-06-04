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
    <AdminFilter
      testId='admin-operations-filters'
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
      surface='card'
      layoutPreset='operations'
      className='mb-5'
      activeFilter={
        activeQuickFilterCard
          ? {
              label: activeFilterLabel,
              value: activeQuickFilterCard.label,
              clearAriaLabel: `${activeQuickFilterCard.label} ${clearLabel}`,
              onClear: () => onQuickFilter(''),
            }
          : null
      }
    />
  );
}

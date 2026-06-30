import { AdminMetricCardGroup } from '@/app/admin/components/AdminMetricCard';
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
    <AdminMetricCardGroup
      title={title}
      items={cards.map(card => ({
        key: card.key,
        label: card.label,
        value: formatCount(card.value, locale),
        tooltip: card.tooltip,
        onClick: () => onQuickFilter(card.quickFilterKey),
      }))}
      gridClassName='md:grid-cols-2 xl:grid-cols-3 min-[1680px]:grid-cols-6'
      cardHoverMode='control'
      tooltipDelayDuration={0}
    />
  );
}

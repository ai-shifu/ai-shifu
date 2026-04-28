import type { EChartsOption } from 'echarts';
import type { DashboardCourseDetailFollowUpCountBySection } from '@/types/dashboard';

export const ALL_CHAPTER_FILTER_VALUE = '__all__';

const FOLLOW_UP_SECTION_TOP_LIMIT = 20;
const MAX_AXIS_LABEL_LENGTH = 18;

export type FollowUpSectionChartLabels = {
  allChapters: string;
  followUpCountSeries: string;
  otherSections: string;
  unassignedSection: string;
  untitledChapter: string;
  untitledSection: string;
};

export type FollowUpChapterOption = {
  value: string;
  label: string;
};

export type FollowUpSectionChartRow = {
  key: string;
  chapterBid: string;
  chapterTitle: string;
  sectionTitle: string;
  label: string;
  followUpCount: number;
  isOther?: boolean;
  isUnassigned?: boolean;
};

type NormalizedFollowUpSectionChartRow = FollowUpSectionChartRow & {
  originalIndex: number;
};

export const buildFollowUpChapterOptions = (
  sections: DashboardCourseDetailFollowUpCountBySection[],
  labels: FollowUpSectionChartLabels,
): FollowUpChapterOption[] => {
  const options = [
    {
      value: ALL_CHAPTER_FILTER_VALUE,
      label: labels.allChapters,
    },
  ];
  const seenChapterBids = new Set<string>();

  sections.forEach(section => {
    const chapterBid = section.chapter_outline_item_bid.trim();
    if (
      !chapterBid ||
      section.is_unassigned ||
      seenChapterBids.has(chapterBid)
    ) {
      return;
    }
    seenChapterBids.add(chapterBid);
    options.push({
      value: chapterBid,
      label: section.chapter_title || labels.untitledChapter,
    });
  });

  return options;
};

export const buildFollowUpSectionRows = (
  sections: DashboardCourseDetailFollowUpCountBySection[],
  selectedChapter: string,
  labels: FollowUpSectionChartLabels,
): FollowUpSectionChartRow[] => {
  const normalizedRows = sections.map((section, index) =>
    normalizeFollowUpSection(section, index, labels),
  );

  if (selectedChapter !== ALL_CHAPTER_FILTER_VALUE) {
    return normalizedRows
      .filter(row => !row.isUnassigned && row.chapterBid === selectedChapter)
      .map(stripInternalRowFields);
  }

  if (normalizedRows.length <= FOLLOW_UP_SECTION_TOP_LIMIT) {
    return normalizedRows.map(stripInternalRowFields);
  }

  const rankedRows = [...normalizedRows].sort((a, b) => {
    if (b.followUpCount !== a.followUpCount) {
      return b.followUpCount - a.followUpCount;
    }
    return a.originalIndex - b.originalIndex;
  });
  const topRows = rankedRows.slice(0, FOLLOW_UP_SECTION_TOP_LIMIT);
  const otherRows = rankedRows.slice(FOLLOW_UP_SECTION_TOP_LIMIT);
  const otherFollowUpCount = otherRows.reduce(
    (sum, row) => sum + row.followUpCount,
    0,
  );

  return [
    ...topRows.map(stripInternalRowFields),
    {
      key: '__other__',
      chapterBid: '',
      chapterTitle: '',
      sectionTitle: labels.otherSections,
      label: labels.otherSections,
      followUpCount: otherFollowUpCount,
      isOther: true,
    },
  ];
};

export const buildFollowUpSectionChartOption = (
  rows: FollowUpSectionChartRow[],
  valueName: string,
): EChartsOption => {
  const orderedRows = [...rows].reverse();
  const shouldScroll = orderedRows.length > 12;

  return {
    grid: {
      top: 16,
      left: 28,
      right: shouldScroll ? 54 : 28,
      bottom: 24,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: params => {
        const firstParam = Array.isArray(params) ? params[0] : params;
        const dataIndex =
          typeof firstParam === 'object' &&
          firstParam !== null &&
          'dataIndex' in firstParam
            ? Number(firstParam.dataIndex)
            : 0;
        const row = orderedRows[dataIndex];
        if (!row) {
          return '';
        }
        const safeSectionTitle = escapeHtml(row.sectionTitle);
        if (row.isOther || row.isUnassigned) {
          return `${safeSectionTitle}<br/>${valueName}: ${row.followUpCount}`;
        }
        return `${escapeHtml(row.chapterTitle)} / ${safeSectionTitle}<br/>${valueName}: ${row.followUpCount}`;
      },
    },
    xAxis: {
      type: 'value',
      minInterval: 1,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#eef2f7' } },
      axisLabel: { color: '#64748b' },
    },
    yAxis: {
      type: 'category',
      data: orderedRows.map(row => truncateChartLabel(row.label)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#475569' },
    },
    dataZoom: shouldScroll
      ? [
          {
            type: 'slider',
            yAxisIndex: 0,
            width: 14,
            right: 8,
            startValue: Math.max(orderedRows.length - 12, 0),
            endValue: orderedRows.length - 1,
            filterMode: 'none',
          },
          {
            type: 'inside',
            yAxisIndex: 0,
            filterMode: 'none',
          },
        ]
      : undefined,
    series: [
      {
        type: 'bar',
        name: valueName,
        data: orderedRows.map(row => row.followUpCount),
        barMaxWidth: 22,
        label: {
          show: true,
          position: 'right',
          color: '#334155',
        },
        itemStyle: {
          color: '#2563eb',
          borderRadius: [0, 6, 6, 0],
        },
      },
    ],
  };
};

const normalizeFollowUpSection = (
  section: DashboardCourseDetailFollowUpCountBySection,
  index: number,
  labels: FollowUpSectionChartLabels,
): NormalizedFollowUpSectionChartRow => {
  const sectionTitle = section.is_unassigned
    ? labels.unassignedSection
    : section.section_title || labels.untitledSection;

  return {
    key: section.section_outline_item_bid || `section-${index}`,
    chapterBid: section.chapter_outline_item_bid.trim(),
    chapterTitle: section.chapter_title || labels.untitledChapter,
    sectionTitle,
    label: sectionTitle,
    followUpCount: Number.isFinite(section.follow_up_count)
      ? section.follow_up_count
      : 0,
    isUnassigned: Boolean(section.is_unassigned),
    originalIndex: index,
  };
};

const stripInternalRowFields = ({
  originalIndex: _originalIndex,
  ...row
}: NormalizedFollowUpSectionChartRow): FollowUpSectionChartRow => row;

const truncateChartLabel = (value: string): string => {
  if (value.length <= MAX_AXIS_LABEL_LENGTH) {
    return value;
  }
  return `${value.slice(0, MAX_AXIS_LABEL_LENGTH)}...`;
};

const escapeHtml = (value: string): string =>
  value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

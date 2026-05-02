import type { EChartsOption } from 'echarts';
import type { DashboardCourseDetailSectionChart } from '@/types/dashboard';

const MAX_AXIS_LABEL_LENGTH = 18;
const DATAZOOM_THRESHOLD = 20;

export type SectionChartLabels = {
  learningUserCount: string;
  learningRecordCount: string;
  followUpUserCount: string;
  followUpQuestionCount: string;
};

export const buildSectionLearningChartOption = (
  sections: DashboardCourseDetailSectionChart[],
  labels: SectionChartLabels,
): EChartsOption => {
  const shouldScroll = sections.length > DATAZOOM_THRESHOLD;

  return {
    grid: {
      top: 16,
      left: 28,
      right: 28,
      bottom: shouldScroll ? 80 : 40,
      containLabel: true,
    },
    legend: {
      show: true,
      bottom: shouldScroll ? 50 : 0,
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { color: '#475569', fontSize: 12 },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [];
        if (!items.length) {
          return '';
        }
        const dataIndex =
          typeof items[0] === 'object' &&
          items[0] !== null &&
          'dataIndex' in items[0]
            ? Number(items[0].dataIndex)
            : 0;
        const section = sections[dataIndex];
        if (!section) {
          return '';
        }
        const header =
          section.chapter_title && section.section_title
            ? `${escapeHtml(section.chapter_title)} / ${escapeHtml(section.section_title)}`
            : escapeHtml(section.section_title || section.chapter_title || '');
        const lines = [
          header,
          `${labels.learningUserCount}: ${section.learning_user_count}`,
          `${labels.learningRecordCount}: ${section.learning_record_count}`,
          `${labels.followUpUserCount}: ${section.follow_up_user_count}`,
          `${labels.followUpQuestionCount}: ${section.follow_up_question_count}`,
        ];
        return lines.join('<br/>');
      },
    },
    xAxis: {
      type: 'category',
      data: sections.map(s => truncateChartLabel(s.section_title)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#475569' },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#eef2f7' } },
      axisLabel: { color: '#64748b' },
    },
    dataZoom: shouldScroll
      ? [
          {
            type: 'slider',
            xAxisIndex: 0,
            height: 14,
            bottom: 12,
            start: 0,
            end: Math.min(
              ((DATAZOOM_THRESHOLD - 1) / sections.length) * 100,
              100,
            ),
            filterMode: 'none',
          },
        ]
      : undefined,
    series: (
      [
        [labels.learningUserCount, (s: DashboardCourseDetailSectionChart) => s.learning_user_count, '#2563eb'],
        [labels.learningRecordCount, (s: DashboardCourseDetailSectionChart) => s.learning_record_count, '#60a5fa'],
        [labels.followUpUserCount, (s: DashboardCourseDetailSectionChart) => s.follow_up_user_count, '#16a34a'],
        [labels.followUpQuestionCount, (s: DashboardCourseDetailSectionChart) => s.follow_up_question_count, '#86efac'],
      ] as const
    ).map(([name, extract, color]) => ({
      type: 'bar',
      name,
      data: sections.map(extract),
      stack: 'total',
      barMaxWidth: 32,
      itemStyle: { color },
    })),
  };
};

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

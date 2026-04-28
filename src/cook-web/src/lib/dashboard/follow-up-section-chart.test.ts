import {
  ALL_CHAPTER_FILTER_VALUE,
  buildFollowUpChapterOptions,
  buildFollowUpSectionChartOption,
  buildFollowUpSectionRows,
  type FollowUpSectionChartLabels,
} from './follow-up-section-chart';

const labels: FollowUpSectionChartLabels = {
  allChapters: 'All Chapters',
  followUpCountSeries: 'Follow-up Questions',
  otherSections: 'Other Sections',
  unassignedSection: 'Unassigned Section',
  untitledChapter: 'Untitled Chapter',
  untitledSection: 'Untitled Section',
};

describe('follow-up section chart helpers', () => {
  test('normalizes chapter bids consistently for options and filtering', () => {
    const sections = [
      {
        chapter_outline_item_bid: ' chapter-1 ',
        chapter_title: 'Chapter 1',
        section_outline_item_bid: 'lesson-1',
        section_title: 'Lesson 1',
        position: '1.1',
        follow_up_count: 3,
      },
    ];

    expect(buildFollowUpChapterOptions(sections, labels)).toEqual([
      { value: ALL_CHAPTER_FILTER_VALUE, label: 'All Chapters' },
      { value: 'chapter-1', label: 'Chapter 1' },
    ]);
    expect(buildFollowUpSectionRows(sections, 'chapter-1', labels)).toEqual([
      {
        key: 'lesson-1',
        chapterBid: 'chapter-1',
        chapterTitle: 'Chapter 1',
        sectionTitle: 'Lesson 1',
        label: 'Lesson 1',
        followUpCount: 3,
        isUnassigned: false,
      },
    ]);
  });

  test('escapes API-provided titles in tooltip HTML', () => {
    const option = buildFollowUpSectionChartOption(
      [
        {
          key: 'lesson-1',
          chapterBid: 'chapter-1',
          chapterTitle: '<img src=x onerror=alert(1)>',
          sectionTitle: 'Lesson <script>alert(1)</script>',
          label: 'Lesson <script>alert(1)</script>',
          followUpCount: 3,
        },
      ],
      labels.followUpCountSeries,
    );
    const tooltip = option.tooltip as {
      formatter: (params: { dataIndex: number }) => string;
    };

    expect(tooltip.formatter({ dataIndex: 0 })).toBe(
      '&lt;img src=x onerror=alert(1)&gt; / Lesson &lt;script&gt;alert(1)&lt;/script&gt;<br/>Follow-up Questions: 3',
    );
  });
});

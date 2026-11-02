import {
  formatDisplayValue,
  hasChapterHierarchy,
  hasDistinctChapterTitle,
  resolvePrimaryAccount,
  resolvePrimaryLessonDisplay,
  resolveSecondaryChapterDisplay,
  splitTimestampValue,
} from './course-feedback-display';

describe('course feedback display helpers', () => {
  test('formatDisplayValue trims and falls back to the empty value', () => {
    expect(formatDisplayValue('  value  ', '--')).toBe('value');
    expect(formatDisplayValue('   ', '--')).toBe('--');
    expect(formatDisplayValue(undefined, '--')).toBe('--');
    expect(formatDisplayValue(null, '--')).toBe('--');
  });

  test('resolvePrimaryAccount prefers the configured identifier', () => {
    const values = {
      mobile: '13800000000',
      email: 'learner@example.com',
      userBid: 'user-1',
      emptyValue: '--',
    };
    expect(
      resolvePrimaryAccount({ ...values, displayIdentifierType: 'phone' }),
    ).toBe('13800000000');
    expect(
      resolvePrimaryAccount({ ...values, displayIdentifierType: 'email' }),
    ).toBe('learner@example.com');
    expect(
      resolvePrimaryAccount({
        ...values,
        email: '',
        displayIdentifierType: 'email',
      }),
    ).toBe('13800000000');
    expect(
      resolvePrimaryAccount({
        ...values,
        mobile: '',
        email: '',
        displayIdentifierType: 'phone',
      }),
    ).toBe('user-1');
    expect(
      resolvePrimaryAccount({
        emptyValue: '--',
        displayIdentifierType: 'phone',
      }),
    ).toBe('--');
  });

  test('lesson and chapter display helpers hide redundant chapter titles', () => {
    expect(
      resolvePrimaryLessonDisplay({
        lessonTitle: 'Lesson 1',
        chapterTitle: 'Chapter 1',
        emptyValue: '--',
      }),
    ).toBe('Lesson 1');
    expect(
      resolvePrimaryLessonDisplay({
        chapterTitle: 'Chapter 1',
        emptyValue: '--',
      }),
    ).toBe('Chapter 1');
    expect(resolvePrimaryLessonDisplay({ emptyValue: '--' })).toBe('--');

    expect(
      resolveSecondaryChapterDisplay({
        chapterTitle: ' Chapter 1 ',
        lessonTitle: 'Lesson 1',
      }),
    ).toBe('Chapter 1');
    expect(
      resolveSecondaryChapterDisplay({
        chapterTitle: 'Same',
        lessonTitle: ' Same ',
      }),
    ).toBe('');
    expect(resolveSecondaryChapterDisplay({ lessonTitle: 'Lesson 1' })).toBe(
      '',
    );
  });

  test('chapter hierarchy requires distinct chapter and lesson titles', () => {
    expect(
      hasDistinctChapterTitle({
        chapter_title: 'Chapter 1',
        lesson_title: 'Lesson 1',
      }),
    ).toBe(true);
    expect(
      hasDistinctChapterTitle({ chapter_title: 'Same', lesson_title: 'Same' }),
    ).toBe(false);
    expect(hasDistinctChapterTitle({ chapter_title: 'Chapter 1' })).toBe(false);

    expect(hasChapterHierarchy([])).toBe(false);
    expect(
      hasChapterHierarchy([
        { chapter_title: 'Same', lesson_title: 'Same' },
        { chapter_title: 'Chapter 1', lesson_title: 'Lesson 1' },
      ]),
    ).toBe(true);
  });

  test('splitTimestampValue splits date and time parts', () => {
    expect(splitTimestampValue('2026-10-01 08:30:00')).toEqual([
      '2026-10-01',
      '08:30:00',
    ]);
    expect(splitTimestampValue('Oct 1, 2026, 8:30 AM')).toEqual([
      'Oct 1 2026 8:30 AM',
    ]);
    expect(splitTimestampValue('--')).toEqual(['--']);
    expect(splitTimestampValue('  ')).toEqual([]);
  });
});

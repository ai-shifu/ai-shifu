import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import FollowUpDetailSheet, {
  type FollowUpDetailSheetData,
  type FollowUpDetailSheetLabels,
} from './FollowUpDetailSheet';

const LOADING_LABEL = 'loading';
const RETRY_LABEL = 'retry';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: () => 'UTC',
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div>{LOADING_LABEL}</div>,
}));

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({
    errorMessage,
    onRetry,
  }: {
    errorMessage: string;
    onRetry?: () => void;
  }) => (
    <div>
      <span>{errorMessage}</span>
      <button
        type='button'
        onClick={onRetry}
      >
        {RETRY_LABEL}
      </button>
    </div>
  ),
}));

jest.mock('@/components/ui/Sheet', () => ({
  __esModule: true,
  Sheet: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) =>
    open ? <div>{children}</div> : null,
  SheetContent: ({ children }: React.PropsWithChildren) => (
    <div role='dialog'>{children}</div>
  ),
  SheetHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SheetTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

const BASE_LABELS: FollowUpDetailSheetLabels = {
  title: 'Follow-up detail',
  basicInfoSection: 'Basic info',
  currentRecordSection: 'Current record',
  currentRecordHint: 'Current record hint',
  timelineSection: 'Timeline',
  user: 'User',
  nickname: 'Nickname',
  followUpTime: 'Follow-up time',
  turnIndex: 'Turn',
  turnIndexHelp: 'Turn help',
  currentFollowUp: 'Question',
  currentAnswer: 'Answer',
  timelineCurrent: 'Current',
};

const DETAIL: FollowUpDetailSheetData = {
  basic_info: {
    user_bid: 'user-1',
    mobile: '13800000000',
    email: '',
    nickname: '',
    chapter_title: 'Chapter 1',
    lesson_title: 'Lesson 1',
    created_at: '2026-10-01T08:30:00Z',
    turn_index: 0,
  },
  current_record: {
    follow_up_content: 'Why?',
    answer_content: 'Because.',
    source_output_content: '',
  },
  timeline: [
    {
      role: 'student',
      content: 'Why?',
      created_at: '2026-10-01T08:30:00Z',
      is_current: true,
    },
    {
      role: 'assistant',
      content: 'Because.',
      created_at: '',
      is_current: false,
    },
  ],
};

const renderSheet = (
  overrides: Partial<React.ComponentProps<typeof FollowUpDetailSheet>> = {},
) => {
  const props: React.ComponentProps<typeof FollowUpDetailSheet> = {
    open: true,
    detail: DETAIL,
    loading: false,
    error: null,
    emptyValue: '--',
    displayIdentifierType: 'phone',
    defaultUserName: 'Anonymous',
    labels: BASE_LABELS,
    resolveLessonDisplay: ({ lessonTitle, emptyValue }) =>
      lessonTitle || emptyValue,
    resolveOutlineFieldLabel: () => 'Lesson',
    formatTurnIndex: turnIndex =>
      turnIndex == null ? '--' : `Turn ${turnIndex}`,
    resolveRoleLabel: role => `role:${role}`,
    onRetry: jest.fn(),
    onOpenChange: jest.fn(),
    ...overrides,
  };
  return { props, ...render(<FollowUpDetailSheet {...props} />) };
};

describe('FollowUpDetailSheet', () => {
  test('renders the basic configuration without optional rows', () => {
    renderSheet();

    expect(screen.getByText('Follow-up detail')).toBeInTheDocument();
    expect(screen.getByText('13800000000')).toBeInTheDocument();
    expect(screen.getByText('Anonymous')).toBeInTheDocument();
    expect(screen.getByText('Lesson')).toBeInTheDocument();
    expect(screen.getByText('Lesson 1')).toBeInTheDocument();
    expect(screen.getAllByText('2026-10-01 08:30:00')).toHaveLength(2);
    expect(screen.getByText('Turn 0')).toBeInTheDocument();
    expect(screen.getByText('Turn help')).toBeInTheDocument();
    expect(screen.queryByText('User ID')).not.toBeInTheDocument();
    expect(screen.queryByText('Source output')).not.toBeInTheDocument();

    expect(screen.getByText('role:student')).toBeInTheDocument();
    expect(screen.getByText('role:assistant')).toBeInTheDocument();
    expect(screen.getByText('Current')).toBeInTheDocument();
    expect(screen.getByText('--')).toBeInTheDocument();
  });

  test('renders the user id row and source output empty state when configured', () => {
    renderSheet({
      labels: {
        ...BASE_LABELS,
        userId: 'User ID',
        sourceOutput: {
          title: 'Source output',
          unavailable: 'Source unavailable',
        },
      },
      resolveOutlineFieldLabel: ({ chapterTitle }) =>
        chapterTitle ? 'Chapter' : 'Lesson',
    });

    expect(screen.getByText('User ID')).toBeInTheDocument();
    expect(screen.getByText('user-1')).toBeInTheDocument();
    expect(screen.getByText('Chapter')).toBeInTheDocument();
    expect(screen.getByText('Source output')).toBeInTheDocument();
    expect(screen.getByText('Source unavailable')).toBeInTheDocument();
  });

  test('shows loading and error states', () => {
    const onRetry = jest.fn();
    const { rerender, props } = renderSheet({ loading: true, detail: null });
    expect(screen.getByText('loading')).toBeInTheDocument();

    rerender(
      <FollowUpDetailSheet
        {...props}
        loading={false}
        error={{ message: 'Load failed' }}
        onRetry={onRetry}
      />,
    );
    expect(screen.getByText('Load failed')).toBeInTheDocument();
    expect(screen.queryByText('Basic info')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  test('expands long text blocks', () => {
    const longAnswer = 'A'.repeat(120);
    renderSheet({
      detail: {
        ...DETAIL,
        current_record: {
          ...DETAIL.current_record,
          answer_content: longAnswer,
        },
        timeline: [],
      },
    });

    fireEvent.click(screen.getByRole('button', { name: 'common.core.expand' }));
    expect(
      screen.getByRole('button', { name: 'common.core.collapse' }),
    ).toBeInTheDocument();
  });
});

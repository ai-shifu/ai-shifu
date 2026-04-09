import React from 'react';
import { within } from '@testing-library/dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AdminOperationCourseDetailPage from './page';

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockGetAdminOperationCourseDetail = jest.fn();
const mockGetAdminOperationCourseChapterDetail = jest.fn();
const mockCopyText = jest.fn();
const mockToastShow = jest.fn();
const mockToastFail = jest.fn();

const mockUserState = {
  isInitialized: true,
  isGuest: false,
  userInfo: {
    is_operator: true,
  },
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
    push: mockPush,
  }),
  useParams: () => ({
    shifu_bid: 'course-1',
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationCourseDetail: (...args: unknown[]) =>
      mockGetAdminOperationCourseDetail(...args),
    getAdminOperationCourseChapterDetail: (...args: unknown[]) =>
      mockGetAdminOperationCourseChapterDetail(...args),
  },
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (selector: (state: typeof mockUserState) => unknown) =>
    selector(mockUserState),
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: { currencySymbol: string }) => unknown) =>
    selector({ currencySymbol: '¥' }),
}));

jest.mock('@/c-utils/textutils', () => ({
  __esModule: true,
  copyText: (...args: unknown[]) => mockCopyText(...args),
}));

jest.mock('@/hooks/useToast', () => ({
  __esModule: true,
  fail: (...args: unknown[]) => mockToastFail(...args),
  show: (...args: unknown[]) => mockToastShow(...args),
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => {
    const ns = Array.isArray(namespace) ? namespace[0] : namespace;
    return {
      t: (key: string) => (ns && ns !== 'translation' ? `${ns}.${key}` : key),
    };
  },
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

describe('AdminOperationCourseDetailPage', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockPush.mockReset();
    mockGetAdminOperationCourseDetail.mockReset();
    mockGetAdminOperationCourseChapterDetail.mockReset();
    mockCopyText.mockReset();
    mockToastShow.mockReset();
    mockToastFail.mockReset();
    mockUserState.isInitialized = true;
    mockUserState.isGuest = false;
    mockUserState.userInfo = {
      is_operator: true,
    };
    mockCopyText.mockResolvedValue(undefined);
    mockGetAdminOperationCourseChapterDetail.mockResolvedValue({
      outline_item_bid: 'lesson-1',
      title: 'Lesson 1',
      content: 'lesson content',
      llm_system_prompt: 'lesson system prompt',
      llm_system_prompt_source: 'chapter',
    });
    mockGetAdminOperationCourseDetail.mockResolvedValue({
      basic_info: {
        shifu_bid: 'course-1',
        course_name: 'Course One',
        course_status: 'published',
        creator_user_bid: 'creator-1',
        creator_mobile: '13800001234',
        creator_email: '',
        creator_nickname: 'Alice',
        created_at: '2026-04-08 10:00:00',
        updated_at: '2026-04-08 11:00:00',
      },
      metrics: {
        learner_count: 12,
        order_count: 4,
        order_amount: '88',
        follow_up_count: 9,
        rating_score: '4.2',
      },
      chapters: [
        {
          outline_item_bid: 'chapter-1',
          title: 'Chapter 1',
          parent_bid: '',
          position: '1',
          node_type: 'chapter',
          learning_permission: 'guest',
          is_visible: true,
          content_status: 'empty',
          follow_up_count: 3,
          rating_count: 2,
          modifier_user_bid: 'creator-1',
          modifier_mobile: '13800001234',
          modifier_email: '',
          modifier_nickname: 'Alice',
          updated_at: '2026-04-08 11:00:00',
          children: [
            {
              outline_item_bid: 'lesson-1',
              title: 'Lesson 1',
              parent_bid: 'chapter-1',
              position: '1.1',
              node_type: 'lesson',
              learning_permission: 'paid',
              is_visible: false,
              content_status: 'has',
              follow_up_count: 3,
              rating_count: 2,
              modifier_user_bid: 'modifier-1',
              modifier_mobile: '13900001234',
              modifier_email: '',
              modifier_nickname: 'Bob',
              updated_at: '2026-04-08 11:00:00',
              children: [],
            },
          ],
        },
      ],
    });
  });

  test('renders course detail data and can go back', async () => {
    render(<AdminOperationCourseDetailPage />);

    expect(
      await screen.findByText('module.operationsCourse.detail.title'),
    ).toBeInTheDocument();
    expect(mockGetAdminOperationCourseDetail).toHaveBeenCalledWith({
      shifu_bid: 'course-1',
    });

    expect(screen.getByText('Course One')).toBeInTheDocument();
    expect(screen.getAllByText('13800001234').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Alice').length).toBeGreaterThan(0);
    expect(screen.getByText('¥88')).toBeInTheDocument();
    expect(screen.getByText('4.2')).toBeInTheDocument();
    expect(screen.getByText('Chapter 1')).toBeInTheDocument();
    expect(screen.getByText('Lesson 1')).toBeInTheDocument();
    expect(
      screen.getByText(
        'module.operationsCourse.detail.learningPermission.guest',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.detail.visibility.hidden'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.detail.contentStatus.has'),
    ).toBeInTheDocument();
    expect(screen.getByText('13900001234')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getAllByText('3').length).toBeGreaterThan(0);
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.operationsCourse.detail.back',
      }),
    );

    expect(mockPush).toHaveBeenCalledWith('/admin/operations');
  });

  test('opens chapter content dialog and copies detail', async () => {
    render(<AdminOperationCourseDetailPage />);

    await screen.findByText('Course One');

    const lessonRow = screen.getByText('Lesson 1').closest('tr');
    expect(lessonRow).not.toBeNull();

    fireEvent.click(
      within(lessonRow as HTMLElement).getByRole('button', {
        name: 'module.operationsCourse.detail.chaptersTable.detailAction',
      }),
    );

    expect(
      await screen.findByText(
        'module.operationsCourse.detail.contentDetailDialog.title',
      ),
    ).toBeInTheDocument();
    expect(mockGetAdminOperationCourseChapterDetail).toHaveBeenCalledWith({
      shifu_bid: 'course-1',
      outline_item_bid: 'lesson-1',
    });

    const copyButton = screen.getByRole('button', {
      name: 'module.operationsCourse.detail.contentDetailDialog.copy',
    });

    await waitFor(() => {
      expect(copyButton).not.toBeDisabled();
    });

    fireEvent.click(copyButton);

    await waitFor(() => {
      expect(mockCopyText).toHaveBeenCalledWith(
        [
          'module.operationsCourse.detail.contentDetailDialog.sections.content',
          'lesson content',
          '',
          'module.operationsCourse.detail.contentDetailDialog.sections.systemPrompt (module.operationsCourse.detail.contentDetailDialog.sources.chapter)',
          'lesson system prompt',
        ].join('\n'),
      );
    });
    expect(mockToastShow).toHaveBeenCalledWith(
      'module.operationsCourse.detail.contentDetailDialog.copySuccess',
    );
  });

  test('redirects non-operators back to admin', async () => {
    mockUserState.userInfo = {
      is_operator: false,
    };

    render(<AdminOperationCourseDetailPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/admin');
    });
  });

  test('surfaces unknown chapter type values instead of mislabeling them', async () => {
    mockGetAdminOperationCourseDetail.mockResolvedValue({
      basic_info: {
        shifu_bid: 'course-1',
        course_name: 'Course One',
        course_status: 'published',
        creator_user_bid: 'creator-1',
        creator_mobile: '13800001234',
        creator_email: '',
        creator_nickname: 'Alice',
        created_at: '2026-04-08 10:00:00',
        updated_at: '2026-04-08 11:00:00',
      },
      metrics: {
        learner_count: 12,
        order_count: 4,
        order_amount: '88',
        follow_up_count: 9,
        rating_score: '4.2',
      },
      chapters: [
        {
          outline_item_bid: 'chapter-1',
          title: 'Chapter 1',
          parent_bid: '',
          position: '1',
          node_type: 'mystery',
          learning_permission: 'guest',
          is_visible: true,
          content_status: 'empty',
          follow_up_count: 3,
          rating_count: 2,
          modifier_user_bid: 'creator-1',
          modifier_mobile: '13800001234',
          modifier_email: '',
          modifier_nickname: 'Alice',
          updated_at: '2026-04-08 11:00:00',
          children: [],
        },
      ],
    });

    render(<AdminOperationCourseDetailPage />);

    expect(
      await screen.findByText(
        'module.operationsCourse.statusLabels.unknown (mystery)',
      ),
    ).toBeInTheDocument();
  });
});

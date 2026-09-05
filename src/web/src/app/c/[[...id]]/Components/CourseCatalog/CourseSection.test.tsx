import { fireEvent, render, screen } from '@testing-library/react';
import { LEARNING_PERMISSION } from '@/api/studyV2';
import { LESSON_STATUS_VALUE } from '@/constants/courseConstants';
import { CourseSection } from './CourseSection';

const mockUserState = { isLoggedIn: true };
const mockSystemState = { previewMode: false };
const mockOpenPayModal = jest.fn();

jest.mock('@/api/studyV2', () => ({
  LEARNING_PERMISSION: {
    NORMAL: 'normal',
    TRIAL: 'trial',
    GUEST: 'guest',
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/store', () => ({
  useUserStore: (selector: (state: typeof mockUserState) => unknown) =>
    selector(mockUserState),
}));

jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: (selector: (state: typeof mockSystemState) => unknown) =>
    selector(mockSystemState),
}));

jest.mock('@/store/useCourseStore', () => ({
  useCourseStore: (
    selector: (state: { openPayModal: typeof mockOpenPayModal }) => unknown,
  ) => selector({ openPayModal: mockOpenPayModal }),
}));

jest.mock('./ResetChapterButton', () => ({
  __esModule: true,
  default: () => null,
}));

describe('CourseSection navigation acceptance', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUserState.isLoggedIn = true;
    mockSystemState.previewMode = false;
  });

  it('reports navigation only after the lesson passes access guards', () => {
    const onTrySelect = jest.fn();
    const onSelect = jest.fn();

    render(
      <CourseSection
        id='lesson-1'
        name='Private lesson title'
        chapterId='chapter-1'
        type={LEARNING_PERMISSION.TRIAL}
        is_paid
        status_value={LESSON_STATUS_VALUE.LEARNING}
        onTrySelect={onTrySelect}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByText('Private lesson title'));

    expect(onTrySelect).toHaveBeenCalledWith({ id: 'lesson-1' });
    expect(onSelect).toHaveBeenCalledWith({ id: 'lesson-1' });
  });

  it('does not report navigation for locked or paywalled lessons', () => {
    const onTrySelect = jest.fn();
    const onSelect = jest.fn();
    const { rerender } = render(
      <CourseSection
        id='lesson-locked'
        name='Locked lesson title'
        chapterId='chapter-1'
        type={LEARNING_PERMISSION.NORMAL}
        is_paid
        status_value={LESSON_STATUS_VALUE.LOCKED}
        onTrySelect={onTrySelect}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByText('Locked lesson title'));
    expect(onTrySelect).not.toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();

    rerender(
      <CourseSection
        id='lesson-paywalled'
        name='Paywalled lesson title'
        chapterId='chapter-1'
        type={LEARNING_PERMISSION.NORMAL}
        is_paid={false}
        status_value={LESSON_STATUS_VALUE.LEARNING}
        onTrySelect={onTrySelect}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByText('Paywalled lesson title'));

    expect(mockOpenPayModal).toHaveBeenCalledWith({
      type: LEARNING_PERMISSION.NORMAL,
      payload: {
        chapterId: 'chapter-1',
        lessonId: 'lesson-paywalled',
      },
    });
    expect(onTrySelect).not.toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();
  });
});

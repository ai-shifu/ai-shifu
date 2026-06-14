import { fireEvent, render, screen } from '@testing-library/react';
import LearningModeSwitch from './LearningModeSwitch';
import { useSystemStore } from '@/c-store/useSystemStore';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
} from '@/app/c/[[...id]]/events';

const mockCourseStoreState: { courseTtsEnabled: boolean | null } = {
  courseTtsEnabled: true,
};

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  browserLanguage: 'en-US',
  default: {
    t: (key: string) => key,
    language: 'en-US',
    changeLanguage: jest.fn(),
  },
}));

jest.mock('@/c-store/useCourseStore', () => ({
  useCourseStore: (
    selector?: (state: typeof mockCourseStoreState) => unknown,
  ) => (selector ? selector(mockCourseStoreState) : mockCourseStoreState),
}));

jest.mock('./HeaderBetaBadge', () => ({
  __esModule: true,
  default: () => <span data-testid='header-beta-badge' />,
}));

describe('LearningModeSwitch', () => {
  const requestFullscreen = jest.fn();
  const setMockLocation = (href: string) => {
    const url = new URL(href);
    window.location.href = url.toString();
    window.location.pathname = url.pathname;
    window.location.search = url.search;
    window.location.hash = url.hash;
  };

  beforeEach(() => {
    jest.restoreAllMocks();
    requestFullscreen.mockResolvedValue(undefined);
    Object.defineProperty(document.documentElement, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    });
    setMockLocation('http://localhost:3000/c/course-1');
    mockCourseStoreState.courseTtsEnabled = true;
    useSystemStore.setState({
      learningMode: 'read',
      canUseClassroomMode: null,
    });
  });

  it('switches presentation modes without stopping active lesson streams', () => {
    const eventsInOrder: string[] = [];
    const stopListener = () => {
      eventsInOrder.push(`stop:${useSystemStore.getState().learningMode}`);
    };
    events.addEventListener(
      BZ_EVENT_NAMES.STOP_ACTIVE_LESSON_STREAM,
      stopListener,
    );

    try {
      render(<LearningModeSwitch />);

      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.chat.learningModeListen',
        }),
      );
      eventsInOrder.push(`mode:${useSystemStore.getState().learningMode}`);

      expect(eventsInOrder).toEqual(['mode:listen']);
    } finally {
      events.removeEventListener(
        BZ_EVENT_NAMES.STOP_ACTIVE_LESSON_STREAM,
        stopListener,
      );
    }
  });

  it('hides classroom mode until preview access is available', () => {
    render(<LearningModeSwitch />);

    expect(
      screen.queryByRole('button', {
        name: 'module.chat.learningModeClassroom',
      }),
    ).not.toBeInTheDocument();
  });

  it('keeps listen mode available while course TTS availability is unknown', () => {
    mockCourseStoreState.courseTtsEnabled = null;

    render(<LearningModeSwitch />);

    expect(
      screen.getByRole('button', {
        name: 'module.chat.learningModeListen',
      }),
    ).toBeInTheDocument();
  });

  it('enters classroom mode with classroom URL state without fullscreen request', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    useSystemStore.setState({ canUseClassroomMode: true });

    render(<LearningModeSwitch />);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.chat.learningModeClassroom',
      }),
    );

    expect(useSystemStore.getState().learningMode).toBe('classroom');
    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/course-1?mode=classroom',
    );
    expect(requestFullscreen).not.toHaveBeenCalled();
  });

  it('preserves preview mode when switching to classroom mode', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    setMockLocation('http://localhost:3000/c/course-1?preview=true');
    useSystemStore.setState({ canUseClassroomMode: true });

    render(<LearningModeSwitch />);

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.chat.learningModeClassroom',
      }),
    );

    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/course-1?preview=true&mode=classroom',
    );
  });
});

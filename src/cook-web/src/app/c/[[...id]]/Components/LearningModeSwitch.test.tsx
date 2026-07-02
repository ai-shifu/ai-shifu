import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LearningModeSwitch from './LearningModeSwitch';
import { useSystemStore } from '@/c-store/useSystemStore';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
} from '@/app/c/[[...id]]/events';

const mockUseParams = jest.fn(() => ({ id: ['course-1'] }));
const originalLocation = window.location;
const originalRequestFullscreenDescriptor = Object.getOwnPropertyDescriptor(
  document.documentElement,
  'requestFullscreen',
);

const mockCourseStoreState: {
  courseTtsEnabled: boolean | null;
  courseTtsStatusCourseId: string | null;
  courseTtsStatusPreviewMode: boolean | null;
} = {
  courseTtsEnabled: true,
  courseTtsStatusCourseId: 'course-1',
  courseTtsStatusPreviewMode: false,
};

const mockEnvStoreState = {
  courseId: 'course-1',
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

jest.mock('next/navigation', () => ({
  ...jest.requireActual('next/navigation'),
  useParams: () => mockUseParams(),
}));

jest.mock('@/c-store/useCourseStore', () => ({
  useCourseStore: (
    selector?: (state: typeof mockCourseStoreState) => unknown,
  ) => (selector ? selector(mockCourseStoreState) : mockCourseStoreState),
}));

jest.mock('@/c-store/envStore', () => ({
  useEnvStore: (selector?: (state: typeof mockEnvStoreState) => unknown) =>
    selector ? selector(mockEnvStoreState) : mockEnvStoreState,
}));

describe('LearningModeSwitch', () => {
  const requestFullscreen = jest.fn();
  const setMockLocation = (href: string) => {
    const url = new URL(href);
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        href: url.toString(),
        pathname: url.pathname,
        search: url.search,
        hash: url.hash,
      },
    });
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
    mockCourseStoreState.courseTtsStatusCourseId = 'course-1';
    mockCourseStoreState.courseTtsStatusPreviewMode = false;
    mockEnvStoreState.courseId = 'course-1';
    mockUseParams.mockReturnValue({ id: ['course-1'] });
    useSystemStore.setState({
      learningMode: 'read',
      previewMode: false,
      canUseClassroomMode: null,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
    if (originalRequestFullscreenDescriptor) {
      Object.defineProperty(
        document.documentElement,
        'requestFullscreen',
        originalRequestFullscreenDescriptor,
      );
    } else {
      Reflect.deleteProperty(document.documentElement, 'requestFullscreen');
    }
  });

  it('switches presentation modes without stopping active lesson streams', () => {
    const eventsInOrder: string[] = [];
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
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
        screen.getByRole('radio', {
          name: 'module.chat.learningModeListen',
        }),
      );
      eventsInOrder.push(`mode:${useSystemStore.getState().learningMode}`);

      expect(eventsInOrder).toEqual(['mode:listen']);
      expect(replaceStateSpy).toHaveBeenCalledWith(
        window.history.state,
        '',
        '/c/course-1?mode=listen',
      );
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
      screen.queryByRole('radio', {
        name: 'module.chat.learningModeClassroom',
      }),
    ).not.toBeInTheDocument();
  });

  it('keeps active classroom mode visible while classroom access is unresolved', () => {
    useSystemStore.setState({
      learningMode: 'classroom',
      canUseClassroomMode: null,
    });

    render(<LearningModeSwitch />);

    expect(
      screen.getByRole('radiogroup', {
        name: 'module.chat.learningModeToggle',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('radio', {
        name: 'module.chat.learningModeClassroom',
      }),
    ).toHaveAttribute('aria-checked', 'true');
    expect(
      screen.getByRole('radio', {
        name: 'module.chat.learningModeRead',
      }),
    ).toBeInTheDocument();
  });

  it('keeps listen mode available while course TTS availability is unknown', () => {
    mockCourseStoreState.courseTtsEnabled = null;

    render(<LearningModeSwitch />);

    expect(
      screen.getByRole('radio', {
        name: 'module.chat.learningModeListen',
      }),
    ).toBeInTheDocument();
  });

  it('does not hide listen mode from another course stale TTS state', () => {
    mockCourseStoreState.courseTtsEnabled = false;
    mockCourseStoreState.courseTtsStatusCourseId = 'old-course';
    useSystemStore.setState({ canUseClassroomMode: true });

    render(<LearningModeSwitch />);

    expect(
      screen.getByRole('radio', {
        name: 'module.chat.learningModeListen',
      }),
    ).toBeInTheDocument();
  });

  it('does not hide listen mode from stale TTS state for another preview mode', () => {
    mockCourseStoreState.courseTtsEnabled = false;
    mockCourseStoreState.courseTtsStatusCourseId = 'course-1';
    mockCourseStoreState.courseTtsStatusPreviewMode = true;
    useSystemStore.setState({ canUseClassroomMode: true, previewMode: false });

    render(<LearningModeSwitch />);

    expect(
      screen.getByRole('radio', {
        name: 'module.chat.learningModeListen',
      }),
    ).toBeInTheDocument();
  });

  it('renders listen mode first without a beta badge', () => {
    render(<LearningModeSwitch />);

    expect(screen.queryByText('Beta')).not.toBeInTheDocument();
    expect(
      screen
        .getAllByRole('radio')
        .map(radio => radio.getAttribute('aria-label')),
    ).toEqual([
      'module.chat.learningModeListen',
      'module.chat.learningModeRead',
    ]);
  });

  it.each([
    {
      label: 'module.chat.learningModeRead',
      tooltip: 'module.chat.learningModeReadTooltip',
    },
    {
      label: 'module.chat.learningModeListen',
      tooltip: 'module.chat.learningModeListenTooltip',
    },
    {
      label: 'module.chat.learningModeClassroom',
      tooltip: 'module.chat.learningModeClassroomTooltip',
    },
  ])('shows a one-sentence tooltip for $label', async ({ label, tooltip }) => {
    const user = userEvent.setup();
    useSystemStore.setState({ canUseClassroomMode: true });

    render(<LearningModeSwitch />);

    const modeButton = screen.getByRole('radio', { name: label });

    await act(async () => {
      await user.hover(modeButton);
    });

    expect(await screen.findAllByText(tooltip)).not.toHaveLength(0);
  });

  it('enters classroom mode with classroom URL state without fullscreen request', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    useSystemStore.setState({ canUseClassroomMode: true });

    render(<LearningModeSwitch />);

    fireEvent.click(
      screen.getByRole('radio', {
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

  it('writes read mode to URL when switching back from another mode', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    setMockLocation('http://localhost:3000/c/course-1?mode=classroom');
    useSystemStore.setState({
      learningMode: 'classroom',
      canUseClassroomMode: true,
    });

    render(<LearningModeSwitch />);

    fireEvent.click(
      screen.getByRole('radio', {
        name: 'module.chat.learningModeRead',
      }),
    );

    expect(useSystemStore.getState().learningMode).toBe('read');
    expect(replaceStateSpy).toHaveBeenCalledWith(
      window.history.state,
      '',
      '/c/course-1?mode=read',
    );
  });

  it('preserves preview mode when switching to classroom mode', () => {
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState');
    setMockLocation('http://localhost:3000/c/course-1?preview=true');
    useSystemStore.setState({ canUseClassroomMode: true });

    render(<LearningModeSwitch />);

    fireEvent.click(
      screen.getByRole('radio', {
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

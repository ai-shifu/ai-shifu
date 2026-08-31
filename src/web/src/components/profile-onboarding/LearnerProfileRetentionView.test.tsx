import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import {
  LearnerProfileRetentionView,
  RETENTION_AUTOPLAY_INTERVAL_MS,
} from './LearnerProfileRetentionView';

const translate = (key: string, params?: Record<string, string | number>) => {
  if (!params) return key;

  const renderedParams = Object.entries(params)
    .map(([name, value]) => `${name}=${value}`)
    .join(',');
  return `${key}:${renderedParams}`;
};

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: translate }),
}));

const percentageSlideId = 'learner-profile-retention-slide-percentage';
const opportunityCostSlideId =
  'learner-profile-retention-slide-opportunityCost';
const blueSkySlideId = 'learner-profile-retention-slide-blueSky';
const warmUpSlideId = 'learner-profile-retention-slide-warmUp';

describe('LearnerProfileRetentionView', () => {
  const originalMatchMediaDescriptor = Object.getOwnPropertyDescriptor(
    window,
    'matchMedia',
  );
  const originalHiddenDescriptor = Object.getOwnPropertyDescriptor(
    document,
    'hidden',
  );
  const originalVisibilityStateDescriptor = Object.getOwnPropertyDescriptor(
    document,
    'visibilityState',
  );

  let documentIsHidden = false;

  const installMatchMedia = (reducedMotion: boolean) => {
    const listeners = new Set<(event: MediaQueryListEvent) => void>();
    const mediaQueryList = {
      matches: reducedMotion,
      media: '(prefers-reduced-motion: reduce)',
      onchange: null,
      addEventListener: jest.fn(
        (_event: string, listener: (event: MediaQueryListEvent) => void) => {
          listeners.add(listener);
        },
      ),
      removeEventListener: jest.fn(
        (_event: string, listener: (event: MediaQueryListEvent) => void) => {
          listeners.delete(listener);
        },
      ),
      addListener: jest.fn((listener: (event: MediaQueryListEvent) => void) => {
        listeners.add(listener);
      }),
      removeListener: jest.fn(
        (listener: (event: MediaQueryListEvent) => void) => {
          listeners.delete(listener);
        },
      ),
      dispatchEvent: jest.fn(),
    } as unknown as MediaQueryList;

    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: jest.fn(() => mediaQueryList),
    });
  };

  const setDocumentHidden = (hidden: boolean) => {
    documentIsHidden = hidden;
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
  };

  const advance = (milliseconds = RETENTION_AUTOPLAY_INTERVAL_MS) => {
    act(() => {
      jest.advanceTimersByTime(milliseconds);
    });
  };

  const currentSlide = () =>
    screen
      .getByTestId('learner-profile-retention-carousel')
      .querySelector(
        '[data-testid^="learner-profile-retention-slide-"]',
      ) as HTMLElement;

  const fireTouchStart = (element: HTMLElement) => {
    const event = new Event('pointerdown', { bubbles: true });
    Object.defineProperty(event, 'pointerType', { value: 'touch' });
    fireEvent(element, event);
  };

  beforeEach(() => {
    jest.useFakeTimers();
    documentIsHidden = false;
    installMatchMedia(false);
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => documentIsHidden,
    });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => (documentIsHidden ? 'hidden' : 'visible'),
    });
  });

  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();

    if (originalMatchMediaDescriptor) {
      Object.defineProperty(window, 'matchMedia', originalMatchMediaDescriptor);
    } else {
      Reflect.deleteProperty(window, 'matchMedia');
    }
    if (originalHiddenDescriptor) {
      Object.defineProperty(document, 'hidden', originalHiddenDescriptor);
    } else {
      Reflect.deleteProperty(document, 'hidden');
    }
    if (originalVisibilityStateDescriptor) {
      Object.defineProperty(
        document,
        'visibilityState',
        originalVisibilityStateDescriptor,
      );
    } else {
      Reflect.deleteProperty(document, 'visibilityState');
    }
  });

  test('renders one question with three audience-specific text explanations', () => {
    render(<LearnerProfileRetentionView />);

    const slide = screen.getByTestId(percentageSlideId);
    expect(
      within(slide).getByRole('heading', {
        name: 'module.profileOnboarding.dialog.retention.slides.percentage.question',
      }),
    ).toBeInTheDocument();
    expect(within(slide).getAllByRole('article')).toHaveLength(3);
    expect(
      within(slide).getByText(
        'module.profileOnboarding.dialog.retention.slides.percentage.audiences.shopper.body',
      ),
    ).toBeInTheDocument();
    expect(
      within(slide).getByText(
        'module.profileOnboarding.dialog.retention.slides.percentage.audiences.basketballFan.body',
      ),
    ).toBeInTheDocument();
    expect(
      within(slide).getByText(
        'module.profileOnboarding.dialog.retention.slides.percentage.audiences.shopOwner.body',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId(opportunityCostSlideId),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('learner-profile-retention-autoplay'),
    ).not.toBeInTheDocument();
  });

  test('uses a compact desktop type scale and spacing inside the standard dialog frame', () => {
    render(<LearnerProfileRetentionView />);

    const title = screen.getByRole('heading', {
      name: 'module.profileOnboarding.dialog.retention.title',
    });
    const description = screen.getByText(
      'module.profileOnboarding.dialog.retention.description',
    );
    const exampleLead = screen.getByText(
      'module.profileOnboarding.dialog.retention.exampleLead',
    );
    const slide = screen.getByTestId(percentageSlideId);
    const question = within(slide).getByRole('heading', {
      name: 'module.profileOnboarding.dialog.retention.slides.percentage.question',
    });
    const firstArticle = within(slide).getAllByRole('article')[0];
    const audienceLabel = within(firstArticle).getByRole('heading', {
      name: 'module.profileOnboarding.dialog.retention.slides.percentage.audiences.shopper.label',
    });
    const audienceBody = within(firstArticle).getByText(
      'module.profileOnboarding.dialog.retention.slides.percentage.audiences.shopper.body',
    );

    expect(title).toHaveClass('sm:text-3xl', 'sm:leading-9');
    expect(title).not.toHaveClass('sm:text-4xl');
    expect(title).not.toHaveClass('xl:text-5xl');
    expect(description).toHaveClass('sm:text-base', 'sm:leading-6');
    expect(description).not.toHaveClass('sm:text-xl');
    expect(exampleLead).toHaveClass('sm:py-2', 'sm:text-base', 'sm:leading-6');
    expect(exampleLead).not.toHaveClass('sm:text-2xl');
    expect(slide).toHaveClass('sm:px-6', 'sm:py-3', 'lg:px-8');
    expect(slide).not.toHaveClass('sm:py-6');
    expect(slide).not.toHaveClass('lg:px-12');
    expect(question).toHaveClass('sm:text-xl', 'sm:leading-7');
    expect(question).not.toHaveClass('sm:text-3xl');
    expect(firstArticle).toHaveClass('sm:gap-4', 'sm:py-2');
    expect(firstArticle).not.toHaveClass('sm:gap-7');
    expect(firstArticle).not.toHaveClass('sm:py-6');
    expect(audienceLabel).toHaveClass('sm:text-lg', 'sm:leading-7');
    expect(audienceLabel).not.toHaveClass('lg:text-2xl');
    expect(audienceBody).toHaveClass('sm:text-base', 'sm:leading-6');
    expect(audienceBody).not.toHaveClass('lg:text-xl');
  });

  test('auto-advances every eight seconds and wraps from the fourth slide to the first', () => {
    render(<LearnerProfileRetentionView />);

    advance(RETENTION_AUTOPLAY_INTERVAL_MS - 1);
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();
    advance(1);
    expect(screen.getByTestId(opportunityCostSlideId)).toBeInTheDocument();
    advance();
    expect(screen.getByTestId(blueSkySlideId)).toBeInTheDocument();
    advance();
    expect(screen.getByTestId(warmUpSlideId)).toBeInTheDocument();
    advance();
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();
  });

  test('manual previous and next navigation wraps and switches to reader-controlled mode', () => {
    render(<LearnerProfileRetentionView />);

    fireEvent.click(screen.getByTestId('learner-profile-retention-previous'));
    expect(screen.getByTestId(warmUpSlideId)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('learner-profile-retention-next'));
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();
    expect(
      screen.getByTestId('learner-profile-retention-carousel'),
    ).toHaveAttribute('data-autoplay', 'paused');
    advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();
  });

  test.each([
    [
      'hover',
      () => fireEvent.pointerEnter(currentSlide()),
      () => fireEvent.pointerLeave(currentSlide()),
    ],
    [
      'document visibility',
      () => setDocumentHidden(true),
      () => setDocumentHidden(false),
    ],
  ])(
    '%s temporarily pauses and resumes with a complete eight-second interval',
    (_name, pause, resume) => {
      render(<LearnerProfileRetentionView />);

      advance(RETENTION_AUTOPLAY_INTERVAL_MS / 2);
      pause();
      expect(
        screen.getByTestId('learner-profile-retention-carousel'),
      ).toHaveAttribute('data-autoplay', 'temporarily-paused');

      advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
      expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();

      resume();
      expect(
        screen.getByTestId('learner-profile-retention-carousel'),
      ).toHaveAttribute('data-autoplay', 'running');
      advance(RETENTION_AUTOPLAY_INTERVAL_MS - 1);
      expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();
      advance(1);
      expect(screen.getByTestId(opportunityCostSlideId)).toBeInTheDocument();
    },
  );

  test.each([
    ['touch interaction', (slide: HTMLElement) => fireTouchStart(slide)],
    ['wheel scrolling', (slide: HTMLElement) => fireEvent.wheel(slide)],
    ['keyboard focus', (slide: HTMLElement) => fireEvent.focus(slide)],
  ])('%s switches to reader-controlled mode', (_name, interact) => {
    render(<LearnerProfileRetentionView />);

    advance(RETENTION_AUTOPLAY_INTERVAL_MS / 2);
    interact(currentSlide());
    expect(
      screen.getByTestId('learner-profile-retention-carousel'),
    ).toHaveAttribute('data-autoplay', 'paused');
    advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();
  });

  test('hovering or focusing the navigation controls prevents a mid-read change', () => {
    render(<LearnerProfileRetentionView />);

    const next = screen.getByTestId('learner-profile-retention-next');
    fireEvent.pointerEnter(next);
    advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();

    fireEvent.pointerLeave(next);
    fireEvent.focus(next);
    expect(
      screen.getByTestId('learner-profile-retention-carousel'),
    ).toHaveAttribute('data-autoplay', 'paused');
    advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();
  });

  test('wheel interaction in the mobile dialog body switches to reader-controlled mode', () => {
    function ScrollContainerHarness() {
      const scrollContainerRef = React.useRef<HTMLDivElement | null>(null);
      return (
        <div
          ref={scrollContainerRef}
          data-testid='scroll-container'
        >
          <LearnerProfileRetentionView
            scrollContainerRef={scrollContainerRef}
          />
        </div>
      );
    }

    render(<ScrollContainerHarness />);

    advance(RETENTION_AUTOPLAY_INTERVAL_MS / 2);
    fireEvent.wheel(screen.getByTestId('scroll-container'));
    expect(
      screen.getByTestId('learner-profile-retention-carousel'),
    ).toHaveAttribute('data-autoplay', 'paused');
    advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();
  });

  test('a programmatic scroll event does not disable autoplay', () => {
    function ScrollContainerHarness() {
      const scrollContainerRef = React.useRef<HTMLDivElement | null>(null);
      return (
        <div
          ref={scrollContainerRef}
          data-testid='scroll-container'
        >
          <LearnerProfileRetentionView
            scrollContainerRef={scrollContainerRef}
          />
        </div>
      );
    }

    render(<ScrollContainerHarness />);

    fireEvent.scroll(screen.getByTestId('scroll-container'));
    expect(
      screen.getByTestId('learner-profile-retention-carousel'),
    ).toHaveAttribute('data-autoplay', 'running');
    advance();
    expect(screen.getByTestId(opportunityCostSlideId)).toBeInTheDocument();
  });

  test('reduced motion keeps automatic changes off while manual navigation still works', () => {
    installMatchMedia(true);
    render(<LearnerProfileRetentionView />);

    const carousel = screen.getByTestId('learner-profile-retention-carousel');
    expect(carousel).toHaveAttribute('data-autoplay', 'paused');
    expect(currentSlide()).not.toHaveClass('animate-in', 'fade-in-0');
    expect(
      screen.queryByTestId('learner-profile-retention-autoplay'),
    ).not.toBeInTheDocument();

    advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('learner-profile-retention-next'));
    expect(screen.getByTestId(opportunityCostSlideId)).toBeInTheDocument();
    expect(currentSlide()).not.toHaveClass('animate-in', 'fade-in-0');
    advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
    expect(screen.getByTestId(opportunityCostSlideId)).toBeInTheDocument();
  });

  test('automatic changes stay silent while manual navigation updates the live region', () => {
    render(<LearnerProfileRetentionView />);

    const announcement = screen.getByTestId(
      'learner-profile-retention-announcement',
    );
    expect(announcement).toBeEmptyDOMElement();

    advance();
    expect(screen.getByTestId(opportunityCostSlideId)).toBeInTheDocument();
    expect(announcement).toBeEmptyDOMElement();

    fireEvent.click(screen.getByTestId('learner-profile-retention-next'));
    expect(screen.getByTestId(blueSkySlideId)).toBeInTheDocument();
    const manualAnnouncement =
      'module.profileOnboarding.dialog.retention.manualAnnouncement:current=3,total=4,topic=module.profileOnboarding.dialog.retention.slides.blueSky.topic';
    expect(announcement).toHaveTextContent(manualAnnouncement);

    advance();
    expect(screen.getByTestId(blueSkySlideId)).toBeInTheDocument();
    expect(announcement).toHaveTextContent(manualAnnouncement);
  });

  test('repeated manual navigation to the same slide remounts its live announcement', () => {
    render(<LearnerProfileRetentionView />);

    const announcement = screen.getByTestId(
      'learner-profile-retention-announcement',
    );
    const next = screen.getByTestId('learner-profile-retention-next');
    fireEvent.click(next);
    const firstAnnouncement = announcement.firstElementChild;
    const opportunityCostAnnouncement = announcement.textContent;

    fireEvent.click(next);
    fireEvent.click(next);
    fireEvent.click(next);
    fireEvent.click(next);

    expect(announcement.textContent).toBe(opportunityCostAnnouncement);
    expect(announcement.firstElementChild).not.toBe(firstAnnouncement);
  });

  test('temporarily disabling an untouched carousel resumes with a full interval', () => {
    const { rerender } = render(<LearnerProfileRetentionView />);

    advance(RETENTION_AUTOPLAY_INTERVAL_MS / 2);
    rerender(<LearnerProfileRetentionView disabled />);
    advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();

    rerender(<LearnerProfileRetentionView />);
    advance(RETENTION_AUTOPLAY_INTERVAL_MS - 1);
    expect(screen.getByTestId(percentageSlideId)).toBeInTheDocument();
    advance(1);
    expect(screen.getByTestId(opportunityCostSlideId)).toBeInTheDocument();
  });

  test('disabled freezes the slide, disables controls, and clears the timer', () => {
    const { rerender, unmount } = render(<LearnerProfileRetentionView />);

    expect(jest.getTimerCount()).toBe(1);
    fireEvent.click(screen.getByTestId('learner-profile-retention-next'));
    expect(screen.getByTestId(opportunityCostSlideId)).toBeInTheDocument();
    expect(jest.getTimerCount()).toBe(0);
    rerender(<LearnerProfileRetentionView disabled />);

    expect(
      screen.getByTestId('learner-profile-retention-previous'),
    ).toBeDisabled();
    expect(screen.getByTestId('learner-profile-retention-next')).toBeDisabled();
    expect(
      screen.queryByTestId('learner-profile-retention-autoplay'),
    ).not.toBeInTheDocument();
    expect(jest.getTimerCount()).toBe(0);

    advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
    expect(screen.getByTestId(opportunityCostSlideId)).toBeInTheDocument();

    rerender(<LearnerProfileRetentionView />);
    advance(RETENTION_AUTOPLAY_INTERVAL_MS * 2);
    expect(screen.getByTestId(opportunityCostSlideId)).toBeInTheDocument();

    unmount();
    expect(jest.getTimerCount()).toBe(0);
  });
});

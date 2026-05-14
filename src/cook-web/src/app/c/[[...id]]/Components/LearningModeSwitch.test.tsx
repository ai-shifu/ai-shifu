import { fireEvent, render, screen } from '@testing-library/react';
import LearningModeSwitch from './LearningModeSwitch';
import { useSystemStore } from '@/c-store/useSystemStore';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
} from '@/app/c/[[...id]]/events';

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

jest.mock('./HeaderBetaBadge', () => ({
  __esModule: true,
  default: () => <span data-testid='header-beta-badge' />,
}));

describe('LearningModeSwitch', () => {
  beforeEach(() => {
    useSystemStore.setState({ learningMode: 'read' });
  });

  it('stops active lesson streams before switching modes', () => {
    const eventsInOrder: string[] = [];
    const stopListener = (event: Event | CustomEvent<{ reason?: string }>) => {
      const reason = 'detail' in event ? event.detail?.reason : undefined;
      eventsInOrder.push(`stop:${useSystemStore.getState().learningMode}`);
      eventsInOrder.push(`reason:${reason ?? ''}`);
    };
    events.addEventListener(
      BZ_EVENT_NAMES.STOP_ACTIVE_LESSON_STREAM,
      stopListener,
    );

    try {
      render(<LearningModeSwitch />);

      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.chat.learningModeToggle',
        }),
      );
      eventsInOrder.push(`mode:${useSystemStore.getState().learningMode}`);

      expect(eventsInOrder).toEqual([
        'stop:read',
        'reason:learning-mode-switch',
        'mode:listen',
      ]);
    } finally {
      events.removeEventListener(
        BZ_EVENT_NAMES.STOP_ACTIVE_LESSON_STREAM,
        stopListener,
      );
    }
  });
});

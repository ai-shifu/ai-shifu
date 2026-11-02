import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import ShifuCard from './ShifuCard';

const mockTrackEvent = jest.fn();

jest.mock('@/hooks/use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('ShifuCard', () => {
  beforeEach(() => {
    mockTrackEvent.mockReset();
  });

  test('keeps the course actions trigger visible without hover', () => {
    render(
      <ShifuCard
        id='course-1'
        image={undefined}
        title='Course 1'
        description='Course description'
        isFavorite={false}
        onImportActivationRequest={jest.fn()}
      />,
    );

    const actionsTrigger = screen.getByRole('button', {
      name: 'common.core.more',
    });

    expect(actionsTrigger).not.toHaveClass('opacity-0');
    expect(actionsTrigger).toHaveClass('h-8', 'w-8', 'bg-transparent');
    expect(actionsTrigger.closest('a')).toBeNull();
  });

  test('marks the course cover image as decorative', () => {
    const { container } = render(
      <ShifuCard
        id='course-1'
        image='https://example.com/cover.png'
        title='Course 1'
        description='Course description'
        isFavorite={false}
      />,
    );

    expect(screen.queryByRole('img')).toBeNull();

    const cover = container.querySelector(
      'img[src="https://example.com/cover.png"]',
    );
    expect(cover).not.toBeNull();
    expect(cover).toHaveAttribute('alt', '');
    expect(cover).toHaveAttribute('aria-hidden', 'true');
  });
});

const ACTIONS = [
  {
    action: 'activate_learners',
    label: 'module.order.importActivation.action',
    help: 'module.order.importActivation.actionDescription',
  },
  {
    action: 'create_discount_code',
    label: 'module.order.redemptionCodes.action',
    help: 'module.order.redemptionCodes.actionDescription',
  },
  {
    action: 'manage_collaborators',
    label: 'module.shifuSetting.permissionManage',
    help: 'module.shifuSetting.permissionManageHint',
  },
  {
    action: 'archive',
    label: 'module.shifuSetting.archive',
    help: 'module.shifuSetting.archiveHint',
  },
] as const;

const renderActionCard = (
  overrides: Partial<React.ComponentProps<typeof ShifuCard>> = {},
) =>
  render(
    <ShifuCard
      id='private-course-id'
      image='https://private.example.com/cover.png'
      title='Private course title'
      description='Private course description'
      isFavorite={false}
      onImportActivationRequest={jest.fn()}
      onRedemptionCodeRequest={jest.fn()}
      canManagePermissions
      onPermissionRequest={jest.fn()}
      canManageArchive
      onArchiveRequest={jest.fn()}
      {...overrides}
    />,
  );

const pointer = (element: Element, type: string, pointerType = 'mouse') => {
  const event = new MouseEvent(type, { bubbles: true, button: 0 });
  Object.defineProperty(event, 'pointerType', { value: pointerType });
  fireEvent(element, event);
};

const openMenu = () => {
  pointer(
    screen.getByRole('button', { name: 'common.core.more' }),
    'pointerdown',
  );
  return screen.getByRole('menu');
};

describe('course action help', () => {
  beforeEach(() => {
    mockTrackEvent.mockReset();
  });

  test('keeps menu descriptions hidden until a tooltip actually opens', () => {
    renderActionCard();
    expect(mockTrackEvent).not.toHaveBeenCalled();
    const menu = openMenu();

    expect(menu).toHaveClass('min-w-[10rem]');
    expect(screen.getAllByRole('menuitem')).toHaveLength(4);
    for (const action of ACTIONS) {
      const item = screen.getByRole('menuitem', { name: action.label });
      expect(item).toHaveTextContent(action.label);
      expect(item).not.toHaveTextContent(action.help);
      expect(screen.queryByText(action.help)).not.toBeInTheDocument();
    }
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  test('requires 300 ms pointer dwell even when menu navigation focuses the item', () => {
    jest.useFakeTimers();
    const view = renderActionCard();
    try {
      openMenu();
      const item = screen.getByRole('menuitem', { name: ACTIONS[0].label });
      pointer(item, 'pointermove');
      expect(item).toHaveFocus();
      expect(item).toHaveAttribute('data-highlighted');
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
      expect(mockTrackEvent).not.toHaveBeenCalled();
      act(() => jest.advanceTimersByTime(299));
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
      expect(mockTrackEvent).not.toHaveBeenCalled();
      pointer(item, 'pointerout');
      act(() => jest.advanceTimersByTime(300));
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
      expect(mockTrackEvent).not.toHaveBeenCalled();

      pointer(item, 'pointermove');
      act(() => jest.advanceTimersByTime(299));
      expect(mockTrackEvent).not.toHaveBeenCalled();
      act(() => jest.advanceTimersByTime(1));
      expect(screen.getByRole('tooltip')).toHaveTextContent(ACTIONS[0].help);
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    } finally {
      view.unmount();
      jest.useRealTimers();
    }
  });

  test('opens keyboard-focus help immediately without waiting for pointer timers', () => {
    jest.useFakeTimers();
    const view = renderActionCard();
    try {
      openMenu();
      const item = screen.getByRole('menuitem', { name: ACTIONS[0].label });
      act(() => item.focus());
      expect(screen.getByRole('tooltip')).toHaveTextContent(ACTIONS[0].help);
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    } finally {
      view.unmount();
      jest.useRealTimers();
    }
  });

  test.each(ACTIONS)(
    'tracks only the displayed $action tooltip with a safe payload',
    async action => {
      renderActionCard();
      openMenu();
      const item = screen.getByRole('menuitem', { name: action.label });
      pointer(item, 'pointermove');

      await waitFor(() => {
        expect(screen.getByRole('tooltip')).toHaveTextContent(action.help);
      });
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_course_action_help_view',
        {
          surface: 'admin_course_list',
          action: action.action,
        },
      );
      const payload = mockTrackEvent.mock.calls[0][1];
      for (const key of [
        'shifu_bid',
        'title',
        'description',
        'help',
        'email',
        'phone',
        'code',
        'url',
        'error',
      ]) {
        expect(payload).not.toHaveProperty(key);
      }
      const event = JSON.stringify(mockTrackEvent.mock.calls[0]);
      expect(event).not.toContain('private-course-id');
      expect(event).not.toContain('Private course');
      expect(event).not.toContain('private.example.com');
      expect(event).not.toContain(action.help);
    },
  );

  test('opens help with keyboard focus and deduplicates per action until the menu reopens', async () => {
    renderActionCard();
    const trigger = screen.getByRole('button', { name: 'common.core.more' });
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    const firstItem = screen.getByRole('menuitem', { name: ACTIONS[0].label });

    await waitFor(() => expect(firstItem).toHaveFocus());
    expect(screen.getByRole('tooltip')).toHaveTextContent(ACTIONS[0].help);
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(firstItem, { key: 'ArrowDown' });
    const secondItem = screen.getByRole('menuitem', { name: ACTIONS[1].label });
    await waitFor(() => expect(secondItem).toHaveFocus());
    expect(mockTrackEvent).toHaveBeenCalledTimes(2);

    fireEvent.keyDown(secondItem, { key: 'ArrowUp' });
    await waitFor(() => expect(firstItem).toHaveFocus());
    expect(mockTrackEvent).toHaveBeenCalledTimes(2);
    fireEvent.click(firstItem);
    await waitFor(() =>
      expect(screen.queryByRole('menu')).not.toBeInTheDocument(),
    );

    openMenu();
    act(() => screen.getByRole('menuitem', { name: ACTIONS[0].label }).focus());
    await waitFor(() =>
      expect(screen.getByRole('tooltip')).toHaveTextContent(ACTIONS[0].help),
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(3);
    expect(mockTrackEvent).toHaveBeenLastCalledWith(
      'creator_course_action_help_view',
      {
        surface: 'admin_course_list',
        action: 'activate_learners',
      },
    );
  });

  test('reports restore separately and never renders unavailable action help', async () => {
    renderActionCard({
      archived: true,
      onImportActivationRequest: undefined,
      onRedemptionCodeRequest: undefined,
      canManagePermissions: false,
    });
    openMenu();
    expect(screen.getAllByRole('menuitem')).toHaveLength(1);
    for (const action of ACTIONS) {
      expect(
        screen.queryByRole('menuitem', { name: action.label }),
      ).not.toBeInTheDocument();
      expect(screen.queryByText(action.help)).not.toBeInTheDocument();
    }
    const restore = screen.getByRole('menuitem', {
      name: 'module.shifuSetting.unarchive',
    });
    act(() => restore.focus());
    await waitFor(() =>
      expect(screen.getByRole('tooltip')).toHaveTextContent(
        'module.shifuSetting.unarchiveHint',
      ),
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_course_action_help_view',
      {
        surface: 'admin_course_list',
        action: 'restore',
      },
    );
  });

  test.each(['throw', 'reject', 'pending'] as const)(
    'keeps tooltip and action selection working when tracking is %s',
    async failure => {
      if (failure === 'throw')
        mockTrackEvent.mockImplementation(() => {
          throw new Error('Private tracking error');
        });
      if (failure === 'reject')
        mockTrackEvent.mockRejectedValue(new Error('Private tracking error'));
      if (failure === 'pending')
        mockTrackEvent.mockReturnValue(new Promise(() => {}));
      const activate = jest.fn();
      renderActionCard({ onImportActivationRequest: activate });
      openMenu();
      const item = screen.getByRole('menuitem', { name: ACTIONS[0].label });
      act(() => item.focus());
      await waitFor(() =>
        expect(screen.getByRole('tooltip')).toHaveTextContent(ACTIONS[0].help),
      );
      fireEvent.click(item);

      expect(activate).toHaveBeenCalledTimes(1);
      await waitFor(() =>
        expect(screen.queryByRole('menu')).not.toBeInTheDocument(),
      );
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    },
  );

  test('does not expose a menu or emit help events for a card with no actions', () => {
    renderActionCard({
      onImportActivationRequest: undefined,
      onRedemptionCodeRequest: undefined,
      canManagePermissions: false,
      canManageArchive: false,
    });
    expect(
      screen.queryByRole('button', { name: 'common.core.more' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });
});

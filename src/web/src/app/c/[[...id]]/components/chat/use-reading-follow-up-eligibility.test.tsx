import { act, renderHook } from '@testing-library/react';
import { useTracking } from '@/hooks/use-tracking';
import { identifyUmamiUser } from '@/lib/tracking';
import { useUserStore } from '@/store/use-user-store';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import { useReadingFollowUp } from './use-reading-follow-up';
import { useAskStateStore } from './use-ask-state-store';

// The global Jest setup stubs i18next; skip unrelated store translation boot.
jest.mock('@/i18n', () => ({
  __esModule: true,
  default: { changeLanguage: jest.fn(), language: 'en-US' },
}));
jest.mock('sse.js', () => ({ SSE: jest.fn() }));

type DeliveredPayload = Record<string, unknown>;

const items: ChatContentItem[] = [
  {
    type: ChatContentItemType.CONTENT,
    element_bid: 'private-anchor',
    content: 'Private lesson content',
  },
];

const installUmami = () => {
  const delivered: DeliveredPayload[] = [];
  const identify = jest.fn().mockResolvedValue(undefined);
  const track = jest.fn(
    (transform: (payload: DeliveredPayload) => DeliveredPayload) => {
      delivered.push(
        transform({
          hostname: 'app.example.test',
          url: 'https://app.example.test/c/private-course?token=secret',
          referrer: 'https://external.example.test/private?token=secret',
          title: 'Private lesson title',
        }),
      );
    },
  );
  (window as any).umami = { identify, track };
  return { delivered, identify, track };
};

const renderReading = ({
  mobile = false,
  previewMode = false,
  enabled = true,
} = {}) =>
  renderHook(() => {
    const { trackEvent } = useTracking();
    return useReadingFollowUp({
      items,
      eligibleAnchors: new Set(['private-anchor']),
      enabled,
      mobile,
      previewMode,
      rootRef: { current: null },
      scopeKey: 'private-lesson',
      onEnsureAsk: () => {},
      trackEvent,
    });
  });

const identifyLearner = (
  identity: string,
  { isGuest = false, analyticsEnabled = true } = {},
) => {
  useUserStore.setState({
    userInfo: isGuest
      ? null
      : { user_id: identity, analytics_enabled: analyticsEnabled },
    isGuest,
    isLoggedIn: !isGuest,
    isInitialized: true,
  });
  identifyUmamiUser({
    user_id: identity,
    analytics_enabled: analyticsEnabled,
  });
};

beforeEach(() => {
  delete (window as any).umami;
  identifyUmamiUser({ user_id: 'test-reset', analytics_enabled: false });
  useAskStateStore.getState().clearLessonScope();
  Object.assign(window.location, {
    href: 'http://localhost:3000/c/private-course/private-lesson?token=secret#private',
    pathname: '/c/private-course/private-lesson',
    search: '?token=secret',
    hash: '#private',
  });
});

afterEach(() => {
  identifyUmamiUser({ user_id: 'test-reset', analytics_enabled: false });
  delete (window as any).umami;
});

test.each([
  {
    identity: 'guest-session',
    isGuest: true,
    mobile: true,
    entry: 'boundary',
    method: 'close',
  },
  {
    identity: 'member-account',
    isGuest: false,
    mobile: false,
    entry: 'history',
    method: 'continue',
  },
] as const)(
  'delivers the reading family for an eligible $identity through useTracking',
  async ({ identity, isGuest, mobile, entry, method }) => {
    const { delivered, identify } = installUmami();
    await act(async () => identifyLearner(identity, { isGuest }));
    const { result } = renderReading({ mobile });

    await act(async () => result.current.toggle('private-anchor', entry));
    expect(result.current.expandedAnchor).toBe('private-anchor');
    await act(async () => result.current.close(method));
    expect(result.current.expandedAnchor).toBeNull();
    expect(useUserStore.getState()).toMatchObject({
      isGuest,
      isLoggedIn: !isGuest,
    });

    expect(identify).toHaveBeenCalledWith(identity);
    expect(delivered).toEqual([
      {
        hostname: 'app.example.test',
        name: 'learner_read_follow_up_opened',
        data: { surface: mobile ? 'mobile' : 'desktop', entry },
        url: '/c/:dynamic',
        referrer: undefined,
        title: undefined,
      },
      {
        hostname: 'app.example.test',
        name: 'learner_read_follow_up_closed',
        data: { surface: mobile ? 'mobile' : 'desktop', method },
        url: '/c/:dynamic',
        referrer: undefined,
        title: undefined,
      },
    ]);
    expect(JSON.stringify(delivered)).not.toMatch(
      /private|secret|user_id|analytics_enabled/,
    );
  },
);

test('excludes both reading events for an excluded account while keeping open and close usable', async () => {
  const { delivered, identify, track } = installUmami();
  await act(async () =>
    identifyLearner('excluded-account', { analyticsEnabled: false }),
  );
  const { result } = renderReading();

  await act(async () => result.current.toggle('private-anchor', 'boundary'));
  expect(result.current.expandedAnchor).toBe('private-anchor');
  await act(async () => result.current.close('continue'));
  expect(result.current.expandedAnchor).toBeNull();
  expect(identify).not.toHaveBeenCalled();
  expect(track).not.toHaveBeenCalled();
  expect(delivered).toEqual([]);

  await act(async () => identifyLearner('resumed-guest', { isGuest: true }));
  expect(identify).toHaveBeenCalledWith('resumed-guest');
  expect(delivered).toEqual([]);
  await act(async () => result.current.toggle('private-anchor', 'history'));
  await act(async () => result.current.close('close'));
  expect(
    delivered.map(payload => ({ name: payload.name, data: payload.data })),
  ).toEqual([
    {
      name: 'learner_read_follow_up_opened',
      data: { surface: 'desktop', entry: 'history' },
    },
    {
      name: 'learner_read_follow_up_closed',
      data: { surface: 'desktop', method: 'close' },
    },
  ]);
});

test.each([
  { previewMode: true, enabled: true },
  { previewMode: false, enabled: false },
])(
  'retains the reading producer exclusions with real transport: %j',
  async options => {
    const { delivered, identify, track } = installUmami();
    await act(async () => identifyLearner('eligible-member'));
    const { result } = renderReading(options);

    await act(async () => result.current.toggle('private-anchor', 'boundary'));
    expect(result.current.expandedAnchor).toBe(
      options.enabled ? 'private-anchor' : null,
    );
    await act(async () => result.current.close('close'));
    expect(result.current.expandedAnchor).toBeNull();
    expect(identify).toHaveBeenCalledWith('eligible-member');
    expect(track).not.toHaveBeenCalled();
    expect(delivered).toEqual([]);
  },
);

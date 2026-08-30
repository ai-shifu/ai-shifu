import { waitFor } from '@testing-library/react';

type TrackingModule = typeof import('./tracking');
type DeliveredPayload = Record<string, unknown>;

const loadTrackingModule = (): TrackingModule => {
  let loadedModule: TrackingModule | undefined;
  jest.isolateModules(() => {
    loadedModule = jest.requireActual('./tracking') as TrackingModule;
  });
  if (!loadedModule) {
    throw new Error('tracking module did not load');
  }
  return loadedModule;
};

const createDeferred = () => {
  let resolve: (() => void) | undefined;
  const promise = new Promise<void>(resolvePromise => {
    resolve = resolvePromise;
  });
  return {
    promise,
    resolve: () => resolve?.(),
  };
};

const settlePromises = async () => {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
};

const installUmami = ({
  identify = jest.fn().mockResolvedValue(undefined),
  onPayload,
}: {
  identify?: jest.Mock;
  onPayload?: (payload: DeliveredPayload) => void;
} = {}) => {
  const track = jest.fn((transform: unknown) => {
    if (typeof transform !== 'function') {
      throw new Error('unsafe Umami overload used');
    }
    const payload = transform({
      hostname: 'app.example.com',
      referrer: 'https://external.example/private?token=secret',
      title: 'Private course title',
      url: 'https://app.example.com/private?token=secret',
    }) as DeliveredPayload;
    onPayload?.(payload);
  });
  (window as any).umami = { identify, track };
  return { identify, track };
};

describe('tracking transport', () => {
  beforeEach(() => {
    Object.assign(window.location, {
      hash: '#fragment',
      href: 'http://localhost:3000/admin/operations/users/private-user?token=secret#fragment',
      pathname: '/admin/operations/users/private-user',
      search: '?token=secret',
    });
    delete (window as any).umami;
  });

  afterEach(() => {
    delete (window as any).umami;
  });

  it('normalizes URLs to bounded routes without sensitive values', () => {
    const { normalizeTrackingRoute } = loadTrackingModule();

    expect(
      normalizeTrackingRoute(
        'https://name:password@example.com/admin/operations/users/private-user?invite_code=secret#details',
      ),
    ).toBe('/admin/operations/users/:dynamic');
    expect(
      normalizeTrackingRoute('https://example.com/shifu/admin/history'),
    ).toBe('/shifu/:dynamic/history');
    expect(normalizeTrackingRoute('/invite/login?code=secret')).toBe(
      '/invite/:dynamic',
    );
    expect(normalizeTrackingRoute('/c/private-course/private-lesson')).toBe(
      '/c/:dynamic',
    );
    expect(
      normalizeTrackingRoute('/one/two/three/four/five/six/seven/eight/nine'),
    ).toBe(
      '/:dynamic/:dynamic/:dynamic/:dynamic/:dynamic/:dynamic/:dynamic/:more',
    );
  });

  it('identifies only by pseudonymous ID, delivers flat scalars, and does not synthesize pageviews', async () => {
    const delivered: DeliveredPayload[] = [];
    const { identify, track } = installUmami({
      onPayload: payload => delivered.push(payload),
    });
    const { identifyUmamiUser, tracking } = loadTrackingModule();
    const circular: Record<string, unknown> = {};
    circular.self = circular;

    identifyUmamiUser({
      user_id: ' user-1 ',
      name: 'Direct Name',
      state: 'member',
      language: 'zh-CN',
    });
    await tracking('creator_contract_test', {
      array_value: ['private', 'content'],
      boolean_value: true,
      date_value: new Date('2026-08-30T00:00:00Z'),
      finite_number: 42,
      infinite_number: Number.POSITIVE_INFINITY,
      null_value: null,
      object_value: { credential: 'secret' },
      circular_value: circular,
      string_value: 'stable_enum',
      undefined_value: undefined,
    });

    await waitFor(() => {
      expect(
        delivered.some(payload => payload.name === 'creator_contract_test'),
      ).toBe(true);
    });

    expect(identify).toHaveBeenCalledTimes(1);
    expect(identify).toHaveBeenCalledWith('user-1');
    const eventPayload = delivered.find(
      payload => payload.name === 'creator_contract_test',
    );
    expect(eventPayload).toMatchObject({
      data: {
        boolean_value: true,
        finite_number: 42,
        string_value: 'stable_enum',
      },
      referrer: undefined,
      title: undefined,
      url: '/admin/operations/users/:dynamic',
    });
    expect(JSON.stringify(eventPayload)).not.toContain('secret');
    expect(track).toHaveBeenCalledTimes(1);
    expect(delivered.every(payload => payload.name)).toBe(true);
  });

  it('preserves event, key, value, field-count, and JSON size bounds', async () => {
    const delivered: DeliveredPayload[] = [];
    installUmami({ onPayload: payload => delivered.push(payload) });
    const { identifyUmamiUser, tracking } = loadTrackingModule();
    const longKey = 'k'.repeat(80);
    const eventData: Record<string, unknown> = {
      [longKey]: 'v'.repeat(300),
    };
    for (let index = 0; index < 40; index += 1) {
      eventData[`field_${index}`] = `value_${index}`;
    }

    identifyUmamiUser({ user_id: 'limits-user' });
    await tracking('e'.repeat(80), eventData);

    await waitFor(() => {
      expect(delivered.some(payload => payload.name)).toBe(true);
    });
    const eventPayload = delivered.find(payload => payload.name);
    const data = eventPayload?.data as Record<string, unknown>;
    expect(eventPayload?.name).toBe('e'.repeat(50));
    expect(Object.keys(data)).toHaveLength(30);
    expect(data['k'.repeat(64)]).toBe('v'.repeat(240));
    expect(JSON.stringify(data).length).toBeLessThanOrEqual(1024);
  });

  it('drains business events queued before the first identity', async () => {
    const firstIdentify = createDeferred();
    const callOrder: string[] = [];
    const delivered: DeliveredPayload[] = [];
    const identify = jest.fn((userId: string) => {
      callOrder.push(`identify:${userId}`);
      return firstIdentify.promise;
    });
    const { track } = installUmami({
      identify,
      onPayload: payload => {
        delivered.push(payload);
        callOrder.push(`track:${String(payload.name ?? 'pageview')}`);
      },
    });
    const { identifyUmamiUser, tracking } = loadTrackingModule();

    await tracking('queued_during_bootstrap', { surface: 'login' });
    expect(track).not.toHaveBeenCalled();

    identifyUmamiUser({ user_id: 'bootstrap-user' });
    expect(callOrder).toEqual(['identify:bootstrap-user']);
    expect(track).not.toHaveBeenCalled();

    firstIdentify.resolve();
    await waitFor(() => {
      expect(callOrder).toEqual([
        'identify:bootstrap-user',
        'track:queued_during_bootstrap',
      ]);
    });
    expect(delivered).toEqual([
      expect.objectContaining({
        data: { surface: 'login' },
        name: 'queued_during_bootstrap',
        referrer: undefined,
        title: undefined,
        url: '/admin/operations/users/:dynamic',
      }),
    ]);
  });

  it('preserves the current pageview but drops old business events when identity changes', async () => {
    const firstIdentify = createDeferred();
    const secondIdentify = createDeferred();
    const callOrder: string[] = [];
    const delivered: DeliveredPayload[] = [];
    const identify = jest.fn((userId: string) => {
      callOrder.push(`identify:${userId}`);
      return userId === 'user-a'
        ? firstIdentify.promise
        : secondIdentify.promise;
    });
    installUmami({
      identify,
      onPayload: payload => {
        delivered.push(payload);
        callOrder.push(`track:${String(payload.name ?? 'pageview')}`);
      },
    });
    const { identifyUmamiUser, tracking, trackPageview } = loadTrackingModule();

    identifyUmamiUser({ user_id: 'user-a', name: 'Old Name' });
    trackPageview('https://app.example.com/c/course-a?token=secret');
    trackPageview('https://app.example.com/admin/billing?token=secret');
    await tracking('queued_before_switch', { surface: 'admin' });
    identifyUmamiUser({ user_id: 'user-b', name: 'New Name' });

    firstIdentify.resolve();
    await waitFor(() => {
      expect(identify).toHaveBeenCalledWith('user-b');
    });
    expect(callOrder).toEqual(['identify:user-a', 'identify:user-b']);

    await tracking('queued_after_switch', { surface: 'admin' });
    secondIdentify.resolve();
    await waitFor(() => {
      expect(callOrder).toEqual([
        'identify:user-a',
        'identify:user-b',
        'track:pageview',
        'track:queued_after_switch',
      ]);
    });
    expect(callOrder).not.toContain('track:queued_before_switch');
    expect(delivered).toEqual([
      expect.objectContaining({
        referrer: undefined,
        title: undefined,
        url: '/admin/billing',
      }),
      expect.objectContaining({
        data: { surface: 'admin' },
        name: 'queued_after_switch',
        referrer: undefined,
        title: undefined,
        url: '/admin/billing',
      }),
    ]);
    expect(JSON.stringify(delivered)).not.toContain('/c/:dynamic');
  });

  it('does not deliver queued calls until the tracker supports identify', async () => {
    const track = jest.fn();
    (window as any).umami = { track };
    const { flushUmamiIdentify, identifyUmamiUser, tracking, trackPageview } =
      loadTrackingModule();

    identifyUmamiUser({ user_id: 'identified-user' });
    trackPageview();
    await tracking('identity_required', { surface: 'admin' });
    await settlePromises();

    expect(track).not.toHaveBeenCalled();

    const identify = jest.fn().mockResolvedValue(undefined);
    (window as any).umami.identify = identify;
    flushUmamiIdentify();

    await waitFor(() => {
      expect(identify).toHaveBeenCalledWith('identified-user');
      expect(track).toHaveBeenCalledTimes(2);
    });
  });

  it('queues before script readiness, keeps the queue bounded, and drains later', async () => {
    const { flushUmamiIdentify, identifyUmamiUser, tracking, trackPageview } =
      loadTrackingModule();

    identifyUmamiUser({ user_id: 'queued-user' });
    trackPageview();
    await settlePromises();
    for (let index = 0; index < 110; index += 1) {
      await tracking(`queued_event_${index}`, { index });
    }
    await settlePromises();

    const delivered: DeliveredPayload[] = [];
    const { identify, track } = installUmami({
      onPayload: payload => delivered.push(payload),
    });
    flushUmamiIdentify();

    await waitFor(() => {
      expect(track).toHaveBeenCalledTimes(100);
    });
    expect(identify).toHaveBeenCalledWith('queued-user');
    expect(delivered.filter(payload => payload.name).at(0)?.name).toBe(
      'queued_event_11',
    );
    expect(delivered.at(-1)?.name).toBe('queued_event_109');
  });

  it('deduplicates query-only changes but counts dynamic-route transitions safely', async () => {
    const delivered: DeliveredPayload[] = [];
    installUmami({ onPayload: payload => delivered.push(payload) });
    const { identifyUmamiUser, trackPageview } = loadTrackingModule();

    identifyUmamiUser({ user_id: 'pageview-user' });
    await settlePromises();
    trackPageview('https://app.example.com/c/course-a?invite=secret');
    trackPageview('https://app.example.com/c/course-a?invite=changed');
    trackPageview('https://app.example.com/c/course-b#private-fragment');

    expect(delivered).toHaveLength(2);
    expect(delivered[0]).toMatchObject({
      referrer: undefined,
      title: undefined,
      url: '/c/:dynamic',
    });
    expect(delivered[1]).toMatchObject({
      referrer: '/c/:dynamic',
      title: undefined,
      url: '/c/:dynamic',
    });
    expect(JSON.stringify(delivered)).not.toContain('course-a');
    expect(JSON.stringify(delivered)).not.toContain('secret');
  });

  it('stays fail-open and never retries through an unsafe Umami overload', async () => {
    const track = jest.fn((transform: unknown) => {
      expect(typeof transform).toBe('function');
      throw new Error('blocked analytics');
    });
    (window as any).umami = {
      identify: jest.fn().mockResolvedValue(undefined),
      track,
    };
    const { identifyUmamiUser, tracking, trackPageview } = loadTrackingModule();

    identifyUmamiUser({ user_id: 'fail-open-user' });
    await settlePromises();

    trackPageview();
    await expect(
      tracking('analytics_delivery_failed', { outcome: 'failed' }),
    ).resolves.toBeUndefined();
    expect(track).toHaveBeenCalledTimes(2);
    expect(track.mock.calls.every(call => typeof call[0] === 'function')).toBe(
      true,
    );
  });
});

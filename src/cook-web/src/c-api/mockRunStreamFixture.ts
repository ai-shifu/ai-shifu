import { loadStaticTextFixture } from '@/lib/mock-fixture';

type MockRunFixtureEvent = {
  type?: string;
  event_type?: string;
  content?: {
    element_bid?: string;
    is_speakable?: boolean;
    audio_url?: string;
    audio_segments?: unknown[];
    [key: string]: unknown;
  } | null;
  [key: string]: unknown;
};

const MOCK_RUN_FIXTURE_QUERY_KEY = 'mock_run_sse_fixture';
const MOCK_RUN_FIXTURE_MODE = {
  STUCK: 'stuck',
  TEST: 'test',
} as const;
const MOCK_RUN_FIXTURE_URL_BY_MODE = {
  [MOCK_RUN_FIXTURE_MODE.STUCK]: '/mock-fixtures/data.json',
  [MOCK_RUN_FIXTURE_MODE.TEST]: '/mock-fixtures/test/data.json',
} as const;
const MOCK_RUN_FIXTURE_CLOSE_AFTER_PLAYBACK_BY_MODE = {
  [MOCK_RUN_FIXTURE_MODE.STUCK]: false,
  [MOCK_RUN_FIXTURE_MODE.TEST]: true,
} as const;
const MOCK_RUN_FIXTURE_OPEN_DELAY_MS = 120;
const MOCK_RUN_FIXTURE_EVENT_INTERVAL_MS = 36;

export type MockRunFixtureMode =
  (typeof MOCK_RUN_FIXTURE_MODE)[keyof typeof MOCK_RUN_FIXTURE_MODE];

const runFixtureEventsPromiseByMode = new Map<
  MockRunFixtureMode,
  Promise<MockRunFixtureEvent[]>
>();

const isMockRunFixtureMode = (mode: string): mode is MockRunFixtureMode =>
  Object.values(MOCK_RUN_FIXTURE_MODE).includes(mode as MockRunFixtureMode);

const getMockRunFixtureModeFromPageUrl = (): MockRunFixtureMode | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  const mode =
    new URLSearchParams(window.location.search)
      .get(MOCK_RUN_FIXTURE_QUERY_KEY)
      ?.trim()
      .toLowerCase() ?? '';

  return isMockRunFixtureMode(mode) ? mode : null;
};

const hasPlayableFixtureAudio = (record?: MockRunFixtureEvent['content']) =>
  Boolean(record?.audio_url || (record?.audio_segments?.length ?? 0) > 0);

const parseMockRunFixtureText = (rawText: string): MockRunFixtureEvent[] =>
  rawText
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(line => line.startsWith('data:'))
    .flatMap(line => {
      const payloadText = line.slice(5).trim();

      if (!payloadText) {
        return [];
      }

      try {
        return [JSON.parse(payloadText) as MockRunFixtureEvent];
      } catch {
        return [];
      }
    });

const buildStuckRunFixtureEvents = (events: MockRunFixtureEvent[]) => {
  const pendingSpeakableEventIndexByElementBid = new Map<string, number>();

  for (const [eventIndex, event] of events.entries()) {
    if (event?.type !== 'element' || !event.content?.element_bid) {
      continue;
    }

    const currentElementBid = event.content.element_bid;

    if (event.content.is_speakable && !hasPlayableFixtureAudio(event.content)) {
      pendingSpeakableEventIndexByElementBid.set(currentElementBid, eventIndex);
      continue;
    }

    if (!hasPlayableFixtureAudio(event.content)) {
      continue;
    }

    const pendingEventIndex =
      pendingSpeakableEventIndexByElementBid.get(currentElementBid);

    if (pendingEventIndex === undefined) {
      continue;
    }

    // Freeze on the last speakable snapshot without playable audio so the
    // consuming player stays stuck waiting for the stream to continue.
    return events.slice(0, pendingEventIndex + 1);
  }

  return events;
};

const loadRunFixtureEvents = async (mode: MockRunFixtureMode) => {
  if (!runFixtureEventsPromiseByMode.has(mode)) {
    const eventsPromise = loadStaticTextFixture(
      MOCK_RUN_FIXTURE_URL_BY_MODE[mode],
    )
      .then(parseMockRunFixtureText)
      .then(events =>
        mode === MOCK_RUN_FIXTURE_MODE.STUCK
          ? buildStuckRunFixtureEvents(events)
          : events,
      );

    runFixtureEventsPromiseByMode.set(mode, eventsPromise);
  }

  return runFixtureEventsPromiseByMode.get(mode) as Promise<
    MockRunFixtureEvent[]
  >;
};

export const getMockRunFixtureMode = (body: {
  input_type?: string;
  [key: string]: unknown;
}): MockRunFixtureMode | null =>
  body.input_type === 'normal' ? getMockRunFixtureModeFromPageUrl() : null;

export const shouldUseMockStuckRunFixture = (body: {
  input_type?: string;
  [key: string]: unknown;
}) => getMockRunFixtureMode(body) === MOCK_RUN_FIXTURE_MODE.STUCK;

export class MockRunStreamFixtureSource extends EventTarget {
  readyState = 0;

  private isClosed = false;

  private hasStarted = false;

  private timerIds: number[] = [];

  constructor(private readonly mode: MockRunFixtureMode) {
    super();
  }

  close() {
    if (this.isClosed) {
      return;
    }

    this.isClosed = true;
    this.timerIds.forEach(timerId => {
      window.clearTimeout(timerId);
    });
    this.timerIds = [];

    if (this.readyState !== 2) {
      this.readyState = 2;
      this.dispatchEvent(new Event('readystatechange'));
    }
  }

  stream() {
    if (this.hasStarted) {
      return;
    }

    this.hasStarted = true;
    void this.startPlayback();
  }

  private async startPlayback() {
    try {
      const events = await loadRunFixtureEvents(this.mode);
      const shouldCloseAfterPlayback =
        MOCK_RUN_FIXTURE_CLOSE_AFTER_PLAYBACK_BY_MODE[this.mode];

      if (this.isClosed) {
        return;
      }

      const openTimerId = window.setTimeout(() => {
        if (this.isClosed) {
          return;
        }

        this.readyState = 1;
        this.dispatchEvent(new Event('readystatechange'));

        events.forEach((event, index) => {
          const timerId = window.setTimeout(() => {
            if (this.isClosed) {
              return;
            }

            this.dispatchEvent(
              new MessageEvent('message', {
                data: JSON.stringify(event),
              }),
            );

            if (shouldCloseAfterPlayback && index === events.length - 1) {
              this.close();
            }
          }, index * MOCK_RUN_FIXTURE_EVENT_INTERVAL_MS);

          this.timerIds.push(timerId);
        });

        if (shouldCloseAfterPlayback && events.length === 0) {
          this.close();
        }
      }, MOCK_RUN_FIXTURE_OPEN_DELAY_MS);

      this.timerIds.push(openTimerId);
    } catch (error) {
      if (this.isClosed) {
        return;
      }

      const errorEvent = new Event('error');
      Object.assign(errorEvent, {
        detail: error,
        data:
          error instanceof Error ? error.message : 'Mock run fixture failed',
      });
      this.dispatchEvent(errorEvent);
      this.close();
    }
  }
}

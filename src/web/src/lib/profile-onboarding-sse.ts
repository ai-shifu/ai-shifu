import { getResolvedBaseURL } from '@/lib/env-utils';
import {
  dispatchSseBusinessError,
  onSseJson,
  openSseStream,
} from '@/lib/sse-client';

export type ProfileOnboardingStreamEvent = {
  type?: string;
  event_type?: string;
  element_type?: string;
  content?: unknown;
  is_terminal?: boolean;
  generated_block_bid?: string | null;
  interaction_id?: string;
};

export const streamProfileOnboardingRuntime = ({
  path,
  payload,
  language,
  onMessage,
  onError,
}: {
  path: string;
  payload?: Record<string, unknown>;
  language?: string;
  onMessage: (event: ProfileOnboardingStreamEvent) => void;
  onError: (error: unknown) => void;
}) => {
  const source = openSseStream({
    url: `${getResolvedBaseURL()}${path}`,
    method: 'POST',
    payload: payload || {},
    language,
    meta: { skipErrorToast: true },
    onBusinessError: (error, stream) => dispatchSseBusinessError(stream, error),
  });
  let settled = false;
  let closedByConsumer = false;
  const reportTransportError = (error: unknown) => {
    if (settled || closedByConsumer) {
      return;
    }
    settled = true;
    onError(error);
  };
  const closeSource = source.close.bind(source);
  source.close = () => {
    closedByConsumer = true;
    closeSource();
  };

  // Malformed SSE payloads are ignored; a later valid event may still recover.
  onSseJson<ProfileOnboardingStreamEvent>(source, parsed => {
    const eventType = parsed.event_type || parsed.type || '';
    if (eventType === 'done' && parsed.is_terminal === true) {
      settled = true;
    }
    onMessage(parsed);
  });
  source.addEventListener('error', error => reportTransportError(error));
  source.addEventListener('readystatechange', event => {
    const readyState = (event as Event & { readyState?: number }).readyState;
    if ((readyState ?? source.readyState) === 2 && !settled) {
      reportTransportError(
        new Error('Profile onboarding stream closed before a terminal event'),
      );
    }
  });
  source.stream();
  return source;
};

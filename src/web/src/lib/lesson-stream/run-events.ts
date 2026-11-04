/**
 * Readers for the non-element events of the learner run and editor debug
 * streams. Both hooks used to parse these separately and accepted different
 * fields; these accept the union, so either stream can carry either shape.
 */

export type RunStreamEvent = {
  type?: string;
  event_type?: string;
  code?: unknown;
  message?: unknown;
  content?: unknown;
  data?: unknown;
  is_terminal?: unknown;
};

/** An object payload, or a JSON object/array string, as an object. */
export const parseRunEventObject = (
  input: unknown,
): Record<string, unknown> | null => {
  if (input && typeof input === 'object') {
    return input as Record<string, unknown>;
  }
  if (typeof input !== 'string') {
    return null;
  }
  const normalized = input.trim();
  if (!normalized.startsWith('{') && !normalized.startsWith('[')) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(normalized);
    return parsed && typeof parsed === 'object'
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
};

const runEventObject = (event: RunStreamEvent) =>
  parseRunEventObject(event.content) || parseRunEventObject(event.data);

const nonEmptyString = (value: unknown): string =>
  typeof value === 'string' && value ? value : '';

/**
 * The message and business code of an `error` event.
 *
 * Message: a plain (non-JSON) string `content` or `data`; else `content`,
 * `message` or `mdflow` of either object payload; else the event's own
 * `message`; else the raw string payload, so an unrecognized JSON error text
 * is still shown. Code: the event's own, else the first numeric `code` in
 * `content`, then `data` -- each payload is searched on its own.
 */
export const readRunEventError = (
  event: RunStreamEvent,
): { message: string; code: number | undefined } => {
  const payloads = [event.content, event.data].map(parseRunEventObject);
  const plainString = (value: unknown) =>
    typeof value === 'string' && !parseRunEventObject(value) ? value : '';
  const fromPayloads = (field: string) =>
    payloads.map(payload => nonEmptyString(payload?.[field])).find(Boolean) ||
    '';
  const message =
    plainString(event.content) ||
    plainString(event.data) ||
    fromPayloads('content') ||
    fromPayloads('message') ||
    fromPayloads('mdflow') ||
    nonEmptyString(event.message) ||
    nonEmptyString(event.content) ||
    nonEmptyString(event.data);
  const code =
    typeof event.code === 'number'
      ? event.code
      : payloads
          .map(payload => payload?.code)
          .find((value): value is number => typeof value === 'number');
  return { message, code };
};

const readBoolean = (value: unknown): boolean | null => {
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  if (typeof value === 'string') {
    const normalized = value.toLowerCase();
    if (normalized === 'true') {
      return true;
    }
    if (normalized === 'false') {
      return false;
    }
  }
  return null;
};

/**
 * Whether a `done` event ends the request (true), only ends a block (false),
 * or does not say (null). The event's own flag wins over its payload's.
 */
export const readDoneIsTerminal = (event: RunStreamEvent): boolean | null => {
  if ('is_terminal' in event) {
    const flag = readBoolean(event.is_terminal);
    if (flag !== null) {
      return flag;
    }
  }
  const payload = runEventObject(event);
  return payload && 'is_terminal' in payload
    ? readBoolean(payload.is_terminal)
    : null;
};

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
 * The message and business code of an `error` event: a plain string content
 * or data, else `content`/`message`/`mdflow` of an object payload, else the
 * event's own `message`; the code from the event, else from the payload.
 */
export const readRunEventError = (
  event: RunStreamEvent,
): { message: string; code: number | undefined } => {
  const payload = runEventObject(event);
  const message =
    (typeof event.content === 'string' && !parseRunEventObject(event.content)
      ? event.content
      : '') ||
    (typeof event.data === 'string' && !parseRunEventObject(event.data)
      ? event.data
      : '') ||
    nonEmptyString(payload?.content) ||
    nonEmptyString(payload?.message) ||
    nonEmptyString(payload?.mdflow) ||
    nonEmptyString(event.message);
  const code =
    typeof event.code === 'number'
      ? event.code
      : typeof payload?.code === 'number'
        ? payload.code
        : undefined;
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

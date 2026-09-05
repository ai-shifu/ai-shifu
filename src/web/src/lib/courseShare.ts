import { buildCoursePageUrl } from '@/lib/urlUtils';

export type CourseShareMethod = 'native' | 'clipboard';
export type CourseShareOutcome = 'success' | 'cancelled' | 'failed';

export type CourseShareResult = {
  method: CourseShareMethod;
  outcome: CourseShareOutcome;
};

export type CourseSharePayload = {
  title: string;
  text: string;
  url: string;
};

export type CourseShareContent = {
  payload: CourseSharePayload;
  clipboardText: string;
};

type CourseShareNavigator = {
  canShare?: (data?: CourseSharePayload) => boolean;
  share?: (data?: CourseSharePayload) => Promise<void>;
  clipboard?: {
    writeText: (text: string) => Promise<void>;
  };
};

export type CourseShareEnvironment = {
  navigator?: CourseShareNavigator | null;
  document?: Document | null;
};

type BuildCourseShareContentOptions = {
  courseTitle: string;
  courseDescription?: string | null;
  recommendation: string;
  url: string;
};

type FormatCourseShareMessageOptions = Pick<
  BuildCourseShareContentOptions,
  'courseDescription' | 'recommendation' | 'url'
>;

const resolveBrowserOrigin = (origin?: string) => {
  const candidate =
    origin ??
    (typeof window !== 'undefined' ? window.location.origin : undefined);
  if (!candidate) {
    return null;
  }

  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
    return parsed.origin;
  } catch {
    return null;
  }
};

/**
 * Resolve a public course URL without carrying lesson, mode, preview, OAuth,
 * or other page-local state into a share. Root-relative URLs are deliberately
 * resolved only against a trusted HTTP(S) browser origin.
 */
export const normalizeCourseShareUrl = (
  candidate: string | null | undefined,
  origin?: string,
): string | null => {
  const normalized = candidate?.trim();
  if (!normalized) {
    return null;
  }

  let absoluteUrl = normalized;
  if (normalized.startsWith('/')) {
    // Protocol-relative URLs and backslash-normalized host escapes must not be
    // treated as same-origin course paths.
    if (normalized.startsWith('//') || normalized.includes('\\')) {
      return null;
    }

    const safeOrigin = resolveBrowserOrigin(origin);
    if (!safeOrigin) {
      return null;
    }

    try {
      const resolved = new URL(normalized, safeOrigin);
      if (resolved.origin !== safeOrigin) {
        return null;
      }
      absoluteUrl = resolved.toString();
    } catch {
      return null;
    }
  }

  const shareUrl = buildCoursePageUrl(absoluteUrl);
  return shareUrl || null;
};

const getShareTextParts = ({
  courseDescription,
  recommendation,
}: Pick<
  BuildCourseShareContentOptions,
  'courseDescription' | 'recommendation'
>) => {
  const description = courseDescription?.trim() || '';
  return [recommendation, description].filter(Boolean);
};

/** Assemble the exact text copied to the clipboard. */
export const formatCourseShareMessage = ({
  courseDescription,
  recommendation,
  url,
}: FormatCourseShareMessageOptions) =>
  [...getShareTextParts({ courseDescription, recommendation }), url].join(
    '\n\n',
  );

/**
 * Keep native share fields separate while providing the complete clipboard
 * fallback text (recommendation, optional original description, then URL).
 */
export const buildCourseShareContent = ({
  courseTitle,
  courseDescription,
  recommendation,
  url,
}: BuildCourseShareContentOptions): CourseShareContent => ({
  payload: {
    title: courseTitle,
    text: getShareTextParts({ courseDescription, recommendation }).join('\n\n'),
    url,
  },
  clipboardText: formatCourseShareMessage({
    courseDescription,
    recommendation,
    url,
  }),
});

const resolveNavigator = (environment?: CourseShareEnvironment) => {
  if (environment && 'navigator' in environment) {
    return environment.navigator ?? null;
  }
  return typeof navigator !== 'undefined'
    ? (navigator as CourseShareNavigator)
    : null;
};

const resolveDocument = (environment?: CourseShareEnvironment) => {
  if (environment && 'document' in environment) {
    return environment.document ?? null;
  }
  return typeof document !== 'undefined' ? document : null;
};

const copyWithTextArea = (text: string, targetDocument: Document | null) => {
  if (
    !targetDocument?.body ||
    typeof targetDocument.execCommand !== 'function'
  ) {
    return false;
  }

  const textArea = targetDocument.createElement('textarea');
  textArea.value = text;
  textArea.setAttribute('readonly', 'readonly');
  textArea.style.position = 'fixed';
  textArea.style.left = '-9999px';
  textArea.style.top = '0';
  textArea.style.opacity = '0';
  targetDocument.body.appendChild(textArea);

  try {
    textArea.focus();
    textArea.select();
    textArea.setSelectionRange(0, text.length);
    return targetDocument.execCommand('copy');
  } catch {
    return false;
  } finally {
    textArea.remove();
  }
};

/** Clipboard API first, then the guarded legacy copy command. */
export const copyCourseShareText = async (
  text: string,
  environment?: CourseShareEnvironment,
) => {
  const shareNavigator = resolveNavigator(environment);
  if (shareNavigator?.clipboard?.writeText) {
    try {
      await shareNavigator.clipboard.writeText(text);
      return true;
    } catch {
      // Clipboard API may be blocked in insecure contexts and embedded
      // browsers. Continue to the selection-based fallback.
    }
  }

  return copyWithTextArea(text, resolveDocument(environment));
};

const isShareCancellation = (error: unknown) =>
  Boolean(
    error &&
    typeof error === 'object' &&
    'name' in error &&
    (error as { name?: unknown }).name === 'AbortError',
  );

/**
 * Invoke native sharing while the caller's click activation is still live.
 * Unsupported or failed native sharing falls back to copying the full text.
 */
export const shareCourse = async (
  content: CourseShareContent,
  environment?: CourseShareEnvironment,
): Promise<CourseShareResult> => {
  const shareNavigator = resolveNavigator(environment);
  let nativeShareAvailable = typeof shareNavigator?.share === 'function';

  if (nativeShareAvailable && typeof shareNavigator?.canShare === 'function') {
    try {
      nativeShareAvailable = shareNavigator.canShare(content.payload);
    } catch {
      nativeShareAvailable = false;
    }
  }

  if (nativeShareAvailable && shareNavigator?.share) {
    try {
      // Calling share before the first await preserves transient user
      // activation. Analytics must likewise remain fire-and-forget upstream.
      const nativeShare = shareNavigator.share(content.payload);
      await nativeShare;
      return { method: 'native', outcome: 'success' };
    } catch (error) {
      if (isShareCancellation(error)) {
        return { method: 'native', outcome: 'cancelled' };
      }
    }
  }

  const copied = await copyCourseShareText(content.clipboardText, environment);
  return {
    method: 'clipboard',
    outcome: copied ? 'success' : 'failed',
  };
};

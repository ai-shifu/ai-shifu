import {
  normalizeLegacyBlockCompatItem,
  normalizeLegacyBlockCompatList,
} from '@/c-utils/chatUiCompat';

const CUSTOM_BUTTON_AFTER_CONTENT_TAG = '<custom-button-after-content>';
const CUSTOM_BUTTON_AFTER_CONTENT_REGEX =
  /<custom-button-after-content>[\s\S]*?<\/custom-button-after-content>/g;

export const appendCustomButtonAfterContent = (
  content: string | undefined,
  buttonMarkup: string,
): string => {
  const baseContent = content ?? '';

  if (!buttonMarkup) {
    return baseContent;
  }

  if (baseContent.includes(CUSTOM_BUTTON_AFTER_CONTENT_TAG)) {
    return baseContent;
  }

  const trimmedContent = baseContent.trimEnd();
  const endsWithCodeFence =
    trimmedContent.endsWith('```') || trimmedContent.endsWith('~~~');
  const needsLineBreak =
    endsWithCodeFence && !baseContent.endsWith('\n') ? '\n' : '';

  return baseContent + needsLineBreak + buttonMarkup;
};

export const hasCustomButtonAfterContent = (
  content?: string | null,
): boolean => {
  return Boolean(content?.includes(CUSTOM_BUTTON_AFTER_CONTENT_TAG));
};

export const stripCustomButtonAfterContent = (
  content?: string | null,
): string | null | undefined => {
  if (!content) {
    return content;
  }
  if (!hasCustomButtonAfterContent(content)) {
    return content;
  }
  // Remove ask button markup from listen mode content.
  return content.replace(CUSTOM_BUTTON_AFTER_CONTENT_REGEX, '').trimEnd();
};

export const syncCustomButtonAfterContent = ({
  content,
  buttonMarkup,
  shouldShowButton,
}: {
  content?: string | null;
  buttonMarkup: string;
  shouldShowButton: boolean;
}): string => {
  const baseContent = content ?? '';

  if (shouldShowButton) {
    return appendCustomButtonAfterContent(baseContent, buttonMarkup);
  }

  return stripCustomButtonAfterContent(baseContent) ?? '';
};

export const inheritCustomButtonAfterContent = ({
  nextContent,
  previousContent,
  buttonMarkup,
}: {
  nextContent?: string | null;
  previousContent?: string | null;
  buttonMarkup: string;
}): string => {
  const resolvedNextContent = nextContent ?? '';

  if (!hasCustomButtonAfterContent(previousContent)) {
    return resolvedNextContent;
  }

  return appendCustomButtonAfterContent(resolvedNextContent, buttonMarkup);
};

export { normalizeLegacyBlockCompatItem, normalizeLegacyBlockCompatList };

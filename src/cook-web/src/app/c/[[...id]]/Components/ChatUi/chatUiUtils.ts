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

export const stripCustomButtonAfterContent = (
  content?: string | null,
): string | null | undefined => {
  if (!content) {
    return content;
  }
  if (!content.includes(CUSTOM_BUTTON_AFTER_CONTENT_TAG)) {
    return content;
  }
  // Remove ask button markup from listen mode content.
  return content.replace(CUSTOM_BUTTON_AFTER_CONTENT_REGEX, '').trimEnd();
};

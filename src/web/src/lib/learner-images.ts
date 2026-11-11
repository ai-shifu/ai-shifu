import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { getResolvedBaseURL } from './env-utils';

export const MAX_LEARNER_IMAGES = 4;
export const MAX_LEARNER_IMAGE_BYTES = 5 * 1024 * 1024;
export const LEARNER_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

export const splitLearnerImages = (value: string) => {
  const images: string[] = [];
  const text = value.replace(
    /!\[learner-image\]\(([^\s()]+)\)/g,
    (marker, url: string) => {
      if (!/^(?:https?:\/\/|\/(?!\/))/.test(url)) return marker;
      images.push(url);
      return '';
    },
  );
  return { text: images.length ? text.trim() : value, images };
};

export const composeLearnerImages = (text: string, images: string[]) =>
  images.length
    ? [text.trim(), ...images.map(url => `![learner-image](${url})`)]
        .filter(Boolean)
        .join('\n\n')
    : text;

export const splitInteractionImages = (value?: string) => {
  if (!value) return { text: value, images: [] as string[] };
  try {
    const parsed = JSON.parse(value);
    if (typeof parsed.inputText === 'string') {
      const result = splitLearnerImages(parsed.inputText);
      const hasControlValue =
        result.text ||
        parsed.buttonText ||
        (Array.isArray(parsed.selectedValues) &&
          parsed.selectedValues.length > 0);
      return {
        text:
          result.images.length && !hasControlValue
            ? ''
            : JSON.stringify({ ...parsed, inputText: result.text }),
        images: result.images,
      };
    }
  } catch {}
  return splitLearnerImages(value);
};

export const resolveLearnerImageUrl = (url: string) =>
  url.startsWith('/') ? `${getResolvedBaseURL()}${url}` : url;

export const serializeLearnerImageSubmission = (
  content: OnSendContentParams,
) => {
  const { images, ...submission } = content;
  return images?.length
    ? {
        ...submission,
        inputText: composeLearnerImages(submission.inputText ?? '', images),
      }
    : submission;
};

export const toMarkdownFlowImageUserInput = (value?: string) => {
  const { text, images } = splitInteractionImages(value);
  if (!images.length) return value;
  let defaults: Record<string, unknown> = { inputText: text ?? '' };
  if (text) {
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed))
        defaults = parsed;
    } catch {}
  }
  return JSON.stringify({ ...defaults, images });
};

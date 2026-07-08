import { SYS_INTERACTION_TYPE } from '@/c-api/studyV2';

const SYSTEM_INTERACTION_TYPES = Object.values(SYS_INTERACTION_TYPE);
type SystemInteractionType =
  (typeof SYS_INTERACTION_TYPE)[keyof typeof SYS_INTERACTION_TYPE];

export const isSystemInteractionContent = (content?: string | null) =>
  typeof content === 'string' &&
  SYSTEM_INTERACTION_TYPES.some(interactionType =>
    content.includes(interactionType),
  );

export const isPaySystemInteractionContent = (content?: string | null) =>
  typeof content === 'string' && content.includes(SYS_INTERACTION_TYPE.PAY);

const SYSTEM_INTERACTION_LABEL_KEYS: Partial<
  Record<SystemInteractionType, string>
> = {
  [SYS_INTERACTION_TYPE.NEXT_CHAPTER]: 'server.learn.nextChapterButton',
  [SYS_INTERACTION_TYPE.PAY]: 'server.order.checkout',
  [SYS_INTERACTION_TYPE.LOGIN]: 'server.user.login',
};

const SYSTEM_INTERACTION_REGEX = /\?\[([^\]]*?)\/\/(_sys_[a-z_]+)\]/g;

export const localizeSystemInteractionContent = (
  content: string | undefined | null,
  translate: (key: string) => string,
) => {
  if (!content) {
    return content ?? '';
  }

  return content.replace(SYSTEM_INTERACTION_REGEX, (match, _label, action) => {
    const labelKey =
      SYSTEM_INTERACTION_LABEL_KEYS[action as SystemInteractionType];
    if (!labelKey) {
      return match;
    }

    const localizedLabel = translate(labelKey);
    if (!localizedLabel || localizedLabel === labelKey) {
      return match;
    }

    return `?[${localizedLabel}//${action}]`;
  });
};

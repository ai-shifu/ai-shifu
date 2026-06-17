import { SYS_INTERACTION_TYPE } from '@/c-api/studyV2';

export const isSystemInteractionContent = (content?: string | null) =>
  typeof content === 'string' &&
  Object.values(SYS_INTERACTION_TYPE).some(interactionType =>
    content.includes(interactionType),
  );

export const isPaySystemInteractionContent = (content?: string | null) =>
  typeof content === 'string' && content.includes(SYS_INTERACTION_TYPE.PAY);

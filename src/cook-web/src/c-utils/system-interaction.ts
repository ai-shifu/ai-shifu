import { SYS_INTERACTION_TYPE } from '@/c-api/studyV2';

const SYSTEM_INTERACTION_TYPES = Object.values(SYS_INTERACTION_TYPE);

export const isSystemInteractionContent = (content?: string | null) =>
  typeof content === 'string' &&
  SYSTEM_INTERACTION_TYPES.some(interactionType =>
    content.includes(interactionType),
  );

export const isPaySystemInteractionContent = (content?: string | null) =>
  typeof content === 'string' && content.includes(SYS_INTERACTION_TYPE.PAY);

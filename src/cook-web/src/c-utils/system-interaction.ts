import { SYS_INTERACTION_TYPE } from '@/c-api/studyV2';

export const isPaySystemInteractionContent = (content?: string | null) =>
  typeof content === 'string' && content.includes(SYS_INTERACTION_TYPE.PAY);

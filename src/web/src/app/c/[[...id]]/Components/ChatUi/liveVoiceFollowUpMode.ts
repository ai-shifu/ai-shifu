export const resolveLiveVoiceFollowUpAvailability = ({
  followUpMode,
  isClassroomMode,
}: {
  followUpMode: 'text' | 'live_voice' | 'disabled';
  isClassroomMode: boolean;
}) => {
  const configured = followUpMode !== 'text';
  return {
    configured,
    supported: followUpMode === 'live_voice' && !isClassroomMode,
  };
};

export type FollowUpPresentationMode = 'text' | 'live_voice' | 'disabled';

export const resolveFollowUpPresentationMode = ({
  configured,
  supported,
}: {
  configured: boolean;
  supported: boolean;
}): FollowUpPresentationMode => {
  if (!configured) {
    return 'text';
  }
  return supported ? 'live_voice' : 'disabled';
};

export const hasLiveVoiceFollowUpHistory = (askList: unknown): boolean =>
  Array.isArray(askList) && askList.length > 0;

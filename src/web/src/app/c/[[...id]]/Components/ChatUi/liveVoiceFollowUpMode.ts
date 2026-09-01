export const resolveLiveVoiceFollowUpAvailability = ({
  followUpMode,
  isClassroomMode,
}: {
  followUpMode: 'text' | 'live_voice';
  isClassroomMode: boolean;
}) => {
  const configured = followUpMode === 'live_voice';
  return {
    configured,
    supported: configured && !isClassroomMode,
  };
};

export const hasLiveVoiceFollowUpHistory = (askList: unknown): boolean =>
  Array.isArray(askList) && askList.length > 0;

export const shouldPauseCourseAudioForLiveVoice = ({
  open,
  state,
}: {
  open: boolean;
  state: string;
}): boolean => open && state !== 'ended';

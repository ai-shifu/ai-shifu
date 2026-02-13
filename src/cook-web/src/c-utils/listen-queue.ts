type QueuePayload = {
  type?: string;
};

type QueueItem = {
  response?: QueuePayload;
  type?: string;
};

const getQueueItemType = (item: QueueItem): string | undefined =>
  item.response?.type ?? item.type;

const AUDIO_SEGMENT_TYPE = 'audio_segment';
const AUDIO_COMPLETE_TYPE = 'audio_complete';
const CONTENT_TYPE = 'content';
const TEXT_END_TYPE = 'done';

export const isAudioQueueType = (type?: string) =>
  type === AUDIO_SEGMENT_TYPE || type === AUDIO_COMPLETE_TYPE;

export const isVisualQueueType = (type?: string) =>
  type === CONTENT_TYPE || type === TEXT_END_TYPE;

export const pickNextListenQueueIndex = ({
  queue,
  pendingAudioCount,
  isInteractionBlocked,
}: {
  queue: QueueItem[];
  pendingAudioCount: number;
  isInteractionBlocked: boolean;
}): number => {
  if (isInteractionBlocked || queue.length === 0) {
    return -1;
  }

  const headType = getQueueItemType(queue[0]);
  const shouldGateVisualHead =
    pendingAudioCount > 0 && isVisualQueueType(headType);

  if (shouldGateVisualHead) {
    return queue.findIndex(item => isAudioQueueType(getQueueItemType(item)));
  }

  const audioIndex = queue.findIndex(item =>
    isAudioQueueType(getQueueItemType(item)),
  );
  return audioIndex >= 0 ? audioIndex : 0;
};

import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { projectListenModeItems } from './chatUiModeProjection';

const askButtonMarkup =
  '<custom-button-after-content><span>Ask</span></custom-button-after-content>';

describe('chatUiModeProjection', () => {
  it('keeps listen mode content while removing inline ask buttons', () => {
    const items: ChatContentItem[] = [
      {
        type: ChatContentItemType.CONTENT,
        element_bid: 'content-1',
        element_type: 'text',
        content: `Narration${askButtonMarkup}`,
        is_renderable: true,
      },
    ];

    expect(
      projectListenModeItems({ items, askButtonMarkup }).map(item => ({
        element_bid: item.element_bid,
        content: item.content,
      })),
    ).toEqual([
      {
        element_bid: 'content-1',
        content: 'Narration',
      },
    ]);
  });

  it('projects classroom mode to visual slides and interactions only', () => {
    const items: ChatContentItem[] = [
      {
        type: ChatContentItemType.CONTENT,
        element_bid: 'narration-1',
        element_type: 'text',
        content: 'Teacher script that should stay off screen',
        is_renderable: true,
      },
      {
        type: ChatContentItemType.CONTENT,
        element_bid: 'slide-1',
        element_type: 'html',
        content: `<section>Slide</section>${askButtonMarkup}`,
        is_renderable: true,
        is_speakable: true,
        audioUrl: '/tts.mp3',
        audioTracks: [
          {
            position: 0,
            audioUrl: '/tts.mp3',
          },
        ],
        isAudioStreaming: true,
        isAudioBackfillReady: true,
        audioDurationMs: 1200,
        audio_url: '/tts-history.mp3',
        audio_segments: [
          {
            segment_index: 0,
            audio_data: 'abc',
            duration_ms: 1200,
            is_final: true,
          },
        ],
        payload: {
          audio: {
            subtitle_cues: [],
          },
        },
        ask_list: [
          {
            type: ChatContentItemType.ASK,
            element_bid: 'ask-1',
          },
        ],
      },
      {
        type: ChatContentItemType.INTERACTION,
        element_bid: 'interaction-1',
        content: '?[%{{choice}} A | B]',
        is_renderable: false,
      },
      {
        type: ChatContentItemType.ASK,
        element_bid: 'ask-2',
        parent_element_bid: 'slide-1',
      },
    ];

    const projectedItems = projectListenModeItems({
      items,
      askButtonMarkup,
      variant: 'classroom',
    });

    expect(projectedItems.map(item => item.element_bid)).toEqual([
      'slide-1',
      'interaction-1',
    ]);

    const slideItem = projectedItems[0];
    expect(slideItem).toEqual(
      expect.objectContaining({
        content: '<section>Slide</section>',
        is_speakable: false,
      }),
    );
    expect(slideItem.audioUrl).toBeUndefined();
    expect(slideItem.audioTracks).toBeUndefined();
    expect(slideItem.isAudioStreaming).toBeUndefined();
    expect(slideItem.isAudioBackfillReady).toBeUndefined();
    expect(slideItem.audioDurationMs).toBeUndefined();
    expect(slideItem.audio_url).toBeUndefined();
    expect(slideItem.audio_segments).toBeUndefined();
    expect(slideItem.ask_list).toBeUndefined();
    expect(slideItem.payload?.audio).toBeUndefined();
  });
});

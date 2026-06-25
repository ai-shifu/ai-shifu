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

  it('keeps listen projection free of classroom-only visual filtering', () => {
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
        element_bid: 'narration-with-slide-metadata',
        element_type: 'text',
        content: 'Teacher script with visual slide metadata',
        is_renderable: true,
        listenSlides: [
          {
            slide_id: 'slide-meta-1',
            slide_index: 0,
            audio_position: 0,
            visual_kind: 'html',
            segment_type: 'visual',
            segment_content: '<section>Generated slide</section>',
            source_span: [0, 1],
            is_placeholder: false,
          },
        ],
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
        type: ChatContentItemType.CONTENT,
        element_bid: 'image-slide-1',
        element_type: 'image',
        content: '![slide](/slide.png)',
        is_renderable: true,
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
    });

    expect(projectedItems.map(item => item.element_bid)).toEqual([
      'narration-1',
      'narration-with-slide-metadata',
      'slide-1',
      'image-slide-1',
      'interaction-1',
      'ask-2',
    ]);

    const slideItem = projectedItems[2];
    expect(slideItem).toEqual(
      expect.objectContaining({
        content: '<section>Slide</section>',
        is_speakable: true,
        audioUrl: '/tts.mp3',
        audio_url: '/tts-history.mp3',
      }),
    );
    expect(slideItem.audioTracks).toHaveLength(1);
    expect(slideItem.audio_segments).toHaveLength(1);
    expect(slideItem.ask_list).toHaveLength(1);
    expect(slideItem.payload?.audio).toBeDefined();
  });

  it('filters classroom projection to visual content and interactions', () => {
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
        type: ChatContentItemType.CONTENT,
        element_bid: 'image-slide-1',
        element_type: 'image',
        content: '![slide](/slide.png)',
        is_renderable: true,
      },
      {
        type: ChatContentItemType.CONTENT,
        element_bid: 'video-slide-1',
        element_type: 'video' as ChatContentItem['element_type'],
        content: '<iframe data-tag="video" src="/lesson.mp4"></iframe>',
        is_renderable: true,
      },
      {
        type: ChatContentItemType.INTERACTION,
        element_bid: 'interaction-1',
        content: '?[%{{choice}} A | B]',
        is_renderable: false,
      },
      {
        type: ChatContentItemType.LIKE_STATUS,
        element_bid: '',
        parent_element_bid: 'slide-1',
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
      'image-slide-1',
      'video-slide-1',
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

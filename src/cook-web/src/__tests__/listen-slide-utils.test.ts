import type { ListenSlideData } from '@/c-api/studyV2';
import {
  normalizeListenSlideList,
  upsertListenSlide,
} from '@/c-utils/listen-slide-utils';

const makeSlide = (
  slideId: string,
  slideIndex: number,
  patch?: Partial<ListenSlideData>,
): ListenSlideData => ({
  slide_id: slideId,
  generated_block_bid: 'block-1',
  slide_index: slideIndex,
  audio_position: slideIndex,
  visual_kind: 'sandbox',
  segment_type: 'sandbox',
  segment_content: `<div>${slideId}</div>`,
  source_span: [0, 1],
  is_placeholder: false,
  ...patch,
});

describe('listen-slide-utils', () => {
  it('normalizes by slide_id and sorts by slide_index', () => {
    const normalized = normalizeListenSlideList([
      makeSlide('slide-2', 2),
      makeSlide('slide-1', 1),
      makeSlide('slide-2', 0, { segment_content: '<div>latest</div>' }),
    ]);

    expect(normalized.map(slide => slide.slide_id)).toEqual([
      'slide-2',
      'slide-1',
    ]);
    expect(normalized.map(slide => slide.slide_index)).toEqual([0, 1]);
    expect(normalized[0].segment_content).toContain('latest');
  });

  it('upserts new_slide and keeps ordering stable', () => {
    const seed = [makeSlide('slide-1', 1)];
    const withNew = upsertListenSlide(seed, makeSlide('slide-0', 0));
    const withUpdate = upsertListenSlide(
      withNew,
      makeSlide('slide-1', 2, { visual_kind: 'svg' }),
    );

    expect(withNew.map(slide => slide.slide_id)).toEqual([
      'slide-0',
      'slide-1',
    ]);
    expect(withUpdate.map(slide => slide.slide_id)).toEqual([
      'slide-0',
      'slide-1',
    ]);
    expect(withUpdate[1].slide_index).toBe(2);
    expect(withUpdate[1].visual_kind).toBe('svg');
  });
});

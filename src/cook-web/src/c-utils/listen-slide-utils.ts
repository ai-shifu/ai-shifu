import type { ListenSlideData } from '@/c-api/studyV2';

export const normalizeListenSlideList = (
  slides: ListenSlideData[],
): ListenSlideData[] => {
  const dedupedById = new Map<string, ListenSlideData>();
  slides.forEach(slide => {
    const slideId = slide?.slide_id;
    if (!slideId) {
      return;
    }
    dedupedById.set(slideId, slide);
  });
  return Array.from(dedupedById.values()).sort(
    (a, b) => a.slide_index - b.slide_index,
  );
};

export const upsertListenSlide = (
  slides: ListenSlideData[],
  incomingSlide: ListenSlideData,
): ListenSlideData[] => {
  if (!incomingSlide?.slide_id) {
    return normalizeListenSlideList(slides);
  }
  return normalizeListenSlideList([...slides, incomingSlide]);
};

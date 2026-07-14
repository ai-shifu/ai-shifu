export const buildStripeCourseReturnUrl = (
  courseUrl?: string,
  courseId?: string,
) => {
  const canonicalUrl = courseUrl?.trim();
  if (canonicalUrl) {
    return canonicalUrl;
  }

  const canonicalBid = courseId?.trim();
  return canonicalBid ? `/c/${encodeURIComponent(canonicalBid)}` : '/c';
};

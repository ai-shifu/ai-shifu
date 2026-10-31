export function isAllowedCoursePrice(
  price: number,
  minimumPaidCoursePrice: number,
): boolean {
  return (
    Number.isFinite(price) &&
    price >= 0 &&
    (price === 0 || price >= minimumPaidCoursePrice)
  );
}

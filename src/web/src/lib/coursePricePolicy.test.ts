import { isAllowedCoursePrice } from './coursePricePolicy';

describe('course price policy', () => {
  test.each([
    [0, 0.01, true],
    [0.01, 0.01, true],
    [0, 0.5, true],
    [0.49, 0.5, false],
    [0.5, 0.5, true],
    [-0.01, 0.01, false],
  ])('validates %s against positive minimum %s', (price, minimum, expected) => {
    expect(isAllowedCoursePrice(price, minimum)).toBe(expected);
  });
});

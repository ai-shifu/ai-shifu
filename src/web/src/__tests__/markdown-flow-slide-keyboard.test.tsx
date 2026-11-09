import { createEvent, fireEvent, render, screen } from '@testing-library/react';
import { Slide } from 'markdown-flow-ui/slide';

beforeEach(() => {
  jest.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
  jest.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
});
afterEach(() => jest.restoreAllMocks());

it('reserves vertical slide shortcuts for the scroll boundary', async () => {
  const { container } = render(
    <Slide
      markerAutoAdvanceDelay={60_000}
      elementList={['First slide', 'Second slide'].map((label, index) => ({
        type: 'slot',
        content: <a href={`#slide-${index}`}>{label}</a>,
        sequence_number: index + 1,
        is_marker: true,
        is_new: true,
        is_renderable: true,
      }))}
    />,
  );
  const stage = container.querySelector<HTMLElement>('.slide-stage__layer')!;
  // jsdom has no layout or element scrolling.
  stage.scrollTo = jest.fn();
  stage.style.overflowY = 'auto';
  Object.defineProperties(stage, {
    clientHeight: { value: 100 },
    scrollHeight: { value: 500 },
  });

  const pressArrow = (link: HTMLElement, key: 'ArrowDown' | 'ArrowUp') => {
    const event = createEvent.keyDown(link, { key, cancelable: true });
    fireEvent(link, event);
    return event.defaultPrevented;
  };

  const first = await screen.findByRole('link', { name: 'First slide' });
  first.focus();
  stage.scrollTop = 100;
  expect(first).toHaveFocus();
  expect(pressArrow(first, 'ArrowDown')).toBe(false);
  expect(first).toBeVisible();

  stage.scrollTop = 400;
  expect(pressArrow(first, 'ArrowDown')).toBe(true);
  const second = await screen.findByRole('link', { name: 'Second slide' });
  second.focus();
  stage.scrollTop = 100;
  expect(second).toHaveFocus();
  expect(pressArrow(second, 'ArrowUp')).toBe(false);
  expect(second).toBeVisible();

  stage.scrollTop = 0;
  expect(pressArrow(second, 'ArrowUp')).toBe(true);
  expect(
    await screen.findByRole('link', { name: 'First slide' }),
  ).toBeVisible();
});

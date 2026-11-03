import React from 'react';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import { Textarea } from './Textarea';

type ObservedTextarea = {
  callback: ResizeObserverCallback;
  observer: ResizeObserver;
};

describe('Textarea automatic sizing', () => {
  let contentWidth: number;
  let measurementCount: number;
  let observers: ObservedTextarea[];
  let resizeObserverMock: jest.Mock;
  const originalResizeObserver = Object.getOwnPropertyDescriptor(
    globalThis,
    'ResizeObserver',
  );
  const originalScrollHeight = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype,
    'scrollHeight',
  );
  const originalGetComputedStyle = window.getComputedStyle;

  beforeEach(() => {
    contentWidth = 320;
    measurementCount = 0;
    observers = [];

    Object.defineProperty(HTMLTextAreaElement.prototype, 'scrollHeight', {
      configurable: true,
      get(this: HTMLTextAreaElement) {
        measurementCount += 1;
        const charactersPerLine = Math.max(1, Math.floor(contentWidth / 8));
        const displayedValue = this.value || this.placeholder;
        const lineCount = displayedValue
          .split('\n')
          .reduce(
            (total, line) =>
              total + Math.max(1, Math.ceil(line.length / charactersPerLine)),
            0,
          );
        const contentHeight = lineCount * 20 + 16;
        const currentClientHeight =
          (Number.parseFloat(this.style.height) || 0) - 2;
        return Math.max(contentHeight, currentClientHeight);
      },
    });
    jest.spyOn(window, 'getComputedStyle').mockImplementation(element => {
      const computedStyle = originalGetComputedStyle.call(window, element);
      if (element instanceof HTMLTextAreaElement) {
        return Object.assign(computedStyle, {
          lineHeight: '20px',
          paddingTop: '8px',
          paddingBottom: '8px',
          borderTopWidth: '1px',
          borderBottomWidth: '1px',
          boxSizing: 'border-box',
        });
      }
      return computedStyle;
    });
    resizeObserverMock = jest.fn((callback: ResizeObserverCallback) => {
      const observer = {
        observe: jest.fn(),
        unobserve: jest.fn(),
        disconnect: jest.fn(),
      };
      observers.push({ callback, observer });
      return observer;
    });
    Object.defineProperty(globalThis, 'ResizeObserver', {
      configurable: true,
      writable: true,
      value: resizeObserverMock,
    });
  });

  afterEach(() => {
    cleanup();
    jest.restoreAllMocks();
    if (originalScrollHeight) {
      Object.defineProperty(
        HTMLTextAreaElement.prototype,
        'scrollHeight',
        originalScrollHeight,
      );
    } else {
      Reflect.deleteProperty(HTMLTextAreaElement.prototype, 'scrollHeight');
    }
    if (originalResizeObserver) {
      Object.defineProperty(
        globalThis,
        'ResizeObserver',
        originalResizeObserver,
      );
    } else {
      Reflect.deleteProperty(globalThis, 'ResizeObserver');
    }
  });

  const notifyWidth = (input: HTMLTextAreaElement, width: number) => {
    contentWidth = width;
    const { callback, observer } = observers[observers.length - 1];
    act(() => {
      callback(
        [
          {
            target: input,
            contentRect: { width } as DOMRectReadOnly,
            borderBoxSize: [],
            contentBoxSize: [],
            devicePixelContentBoxSize: [],
          },
        ],
        observer,
      );
    });
  };

  test.each([
    ['', 38],
    ['Short answer', 38],
    ['First line\nSecond line', 58],
    ['a'.repeat(80), 58],
  ])(
    'fits initial content %j including padding and borders',
    (value, height) => {
      render(
        <Textarea
          minRows={1}
          value={value}
          readOnly
        />,
      );
      const input = screen.getByRole('textbox');

      expect(input).toHaveAttribute('rows', '1');
      expect(input).toHaveStyle({ height: `${height}px`, overflowY: 'hidden' });
    },
  );

  test('grows for restored multiline values and shrinks after deletion', () => {
    const { rerender } = render(
      <Textarea
        minRows={1}
        value='Short answer'
        readOnly
      />,
    );
    const input = screen.getByRole('textbox');

    rerender(
      <Textarea
        minRows={1}
        value={'First line\nSecond line\nThird line'}
        readOnly
      />,
    );
    expect(input).toHaveStyle({ height: '78px' });

    rerender(
      <Textarea
        minRows={1}
        value='Short again'
        readOnly
      />,
    );
    expect(input).toHaveStyle({ height: '38px', overflowY: 'hidden' });
  });

  test('shrinks an empty value when its localized placeholder becomes shorter', () => {
    const { rerender } = render(
      <Textarea
        minRows={1}
        value=''
        placeholder={'a'.repeat(80)}
        readOnly
      />,
    );
    const input = screen.getByRole('textbox');
    expect(input).toHaveStyle({ height: '58px' });

    rerender(
      <Textarea
        minRows={1}
        value=''
        placeholder='Short placeholder'
        readOnly
      />,
    );
    expect(input).toHaveStyle({ height: '38px', overflowY: 'hidden' });
  });

  test('resizes uncontrolled input while preserving its input callback', () => {
    const onInput = jest.fn();
    render(
      <Textarea
        minRows={1}
        defaultValue='Short answer'
        onInput={onInput}
      />,
    );
    const input = screen.getByRole('textbox');

    fireEvent.input(input, { target: { value: 'First line\nSecond line' } });
    expect(input).toHaveStyle({ height: '58px' });
    fireEvent.input(input, { target: { value: 'Short again' } });
    expect(input).toHaveStyle({ height: '38px' });
    expect(onInput).toHaveBeenCalledTimes(2);
  });

  test('reflows on width changes without measuring height-only notifications', () => {
    const { unmount } = render(
      <Textarea
        minRows={1}
        value={'a'.repeat(80)}
        readOnly
      />,
    );
    const input = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(input).toHaveStyle({ height: '58px' });
    expect(observers[0].observer.observe).toHaveBeenCalledWith(input);

    notifyWidth(input, 160);
    expect(input).toHaveStyle({ height: '98px' });

    const measurementsAfterNarrowing = measurementCount;
    notifyWidth(input, 160);
    expect(measurementCount).toBe(measurementsAfterNarrowing);

    notifyWidth(input, 640);
    expect(input).toHaveStyle({ height: '38px', overflowY: 'hidden' });

    const measurementsAfterWidening = measurementCount;
    notifyWidth(input, 640);
    expect(measurementCount).toBe(measurementsAfterWidening);

    unmount();
    expect(observers[0].observer.disconnect).toHaveBeenCalledTimes(1);
  });

  test('caps long content at maxRows and removes scrolling after shrinking', () => {
    const { rerender } = render(
      <Textarea
        minRows={1}
        maxRows={3}
        value={'a'.repeat(160)}
        readOnly
      />,
    );
    const input = screen.getByRole('textbox');
    expect(input).toHaveStyle({
      height: '78px',
      maxHeight: '78px',
      overflowY: 'auto',
    });

    rerender(
      <Textarea
        minRows={1}
        maxRows={3}
        value='Short answer'
        readOnly
      />,
    );
    expect(input).toHaveStyle({
      height: '38px',
      maxHeight: '78px',
      overflowY: 'hidden',
    });
  });

  test('leaves fixed-row textareas unmeasured and unobserved', () => {
    render(
      <Textarea
        rows={2}
        defaultValue='Fixed rows'
      />,
    );
    const input = screen.getByRole('textbox');

    fireEvent.input(input, { target: { value: 'First line\nSecond line' } });

    expect(input).toHaveAttribute('rows', '2');
    expect(input.style.height).toBe('');
    expect(measurementCount).toBe(0);
    expect(resizeObserverMock).not.toHaveBeenCalled();
  });
});

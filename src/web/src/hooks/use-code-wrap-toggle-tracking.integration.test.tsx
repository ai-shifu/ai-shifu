import React from 'react';
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { deserialize, serialize } from 'node:v8';
import { ContentRender } from 'markdown-flow-ui/renderer';
import { useCodeWrapToggleTracking } from './use-code-wrap-toggle-tracking';

// Uses the installed renderer so a real button press drives the observer.
const mockTrackEvent = jest.fn();
jest.mock('./use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

const codeBlock = ['```js', 'const value = 1;', '```'].join('\n');

function Lesson({ onboarding = false }: { onboarding?: boolean }) {
  useCodeWrapToggleTracking('course_read');
  return (
    <>
      <div data-testid='lesson'>
        <ContentRender content={codeBlock} />
      </div>
      {onboarding ? (
        <div
          data-testid='onboarding'
          data-code-wrap-tracking-excluded='true'
        >
          <ContentRender content={codeBlock} />
        </div>
      ) : null}
    </>
  );
}

const renderLesson = async (onboarding = false) => {
  const view = render(<Lesson onboarding={onboarding} />);
  // The hook imports the renderer on demand; let that import settle.
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0));
  });
  const wrapButton = (testId: string) =>
    view.getByTestId(testId).querySelector<HTMLButtonElement>('.wrap-button')!;
  const isWrapped = (testId: string) =>
    view
      .getByTestId(testId)
      .querySelector('pre')!
      .classList.contains('code-block-pre--wrap');
  return { wrapButton, isWrapped };
};

describe('code wrap toggle tracking with the installed renderer', () => {
  const originalStructuredClone = globalThis.structuredClone;

  beforeAll(() => {
    // Jest 29's JSDOM omits this browser API used to copy the Markdown AST.
    globalThis.structuredClone ??= value => deserialize(serialize(value));
  });

  afterAll(() => {
    globalThis.structuredClone = originalStructuredClone;
  });

  beforeEach(() => {
    mockTrackEvent.mockReset();
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  it('records one event for one press of a lesson wrap button', async () => {
    const { wrapButton, isWrapped } = await renderLesson();

    fireEvent.click(wrapButton('lesson'));

    expect(isWrapped('lesson')).toBe(true);
    expect(mockTrackEvent.mock.calls).toEqual([
      [
        'learner_code_block_wrap_toggled',
        { surface: 'course_read', wrap_enabled: true },
      ],
    ]);
  });

  it.each(['throw', 'reject'])(
    'still wraps the code when tracking fails with a %s',
    async failure => {
      mockTrackEvent.mockImplementation(() => {
        if (failure === 'throw') throw new Error('tracking unavailable');
        return Promise.reject(new Error('tracking unavailable'));
      });
      const { wrapButton, isWrapped } = await renderLesson();

      await act(async () => {
        fireEvent.click(wrapButton('lesson'));
      });
      expect(isWrapped('lesson')).toBe(true);
      expect(wrapButton('lesson').getAttribute('aria-pressed')).toBe('true');

      await act(async () => {
        fireEvent.click(wrapButton('lesson'));
      });
      expect(isWrapped('lesson')).toBe(false);
      expect(mockTrackEvent).toHaveBeenCalledTimes(2);
    },
  );

  it('does not count presses inside an excluded region as lesson use', async () => {
    const { wrapButton, isWrapped } = await renderLesson(true);

    fireEvent.click(wrapButton('onboarding'));

    // The shared preference still applies everywhere; only the event is skipped.
    expect(isWrapped('onboarding')).toBe(true);
    expect(isWrapped('lesson')).toBe(true);
    expect(mockTrackEvent).not.toHaveBeenCalled();

    fireEvent.click(wrapButton('lesson'));

    expect(mockTrackEvent.mock.calls).toEqual([
      [
        'learner_code_block_wrap_toggled',
        { surface: 'course_read', wrap_enabled: false },
      ],
    ]);
  });
});

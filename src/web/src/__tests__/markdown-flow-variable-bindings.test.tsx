import React from 'react';
import { cleanup, fireEvent, render } from '@testing-library/react';
import { deserialize, serialize } from 'node:v8';
import { ContentRender } from 'markdown-flow-ui/renderer';
import { createInteractionParser } from 'remark-flow';
import { resolveInteractionSubmission } from '@/lib/interaction-user-input';

describe('installed MarkdownFlow named-answer bindings', () => {
  const originalStructuredClone = globalThis.structuredClone;

  beforeAll(() => {
    // Exercise the published renderer through the configured parser path.
    globalThis.structuredClone ??= value => deserialize(serialize(value));
  });

  afterAll(() => {
    globalThis.structuredClone = originalStructuredClone;
  });

  afterEach(cleanup);

  it('keeps direct parser imports on their public exports', () => {
    expect(
      createInteractionParser().parseToRemarkFormat('?[{{direct}} A | B]'),
    ).toEqual(
      expect.objectContaining({
        variableName: 'direct',
        buttonTexts: ['A', 'B'],
      }),
    );
  });

  it.each(['{{goal}}', '%{{goal}}'])(
    'submits and restores the named answer for %s',
    marker => {
      const content = `?[${marker} A//a | B//b]`;
      const onSend = jest.fn();
      const view = render(
        <ContentRender
          content={content}
          onSend={onSend}
        />,
      );

      fireEvent.click(view.getByText('B'));

      expect(onSend).toHaveBeenCalledTimes(1);
      expect(onSend.mock.calls[0][0]).toEqual(
        expect.objectContaining({ variableName: 'goal' }),
      );
      const submission = resolveInteractionSubmission(onSend.mock.calls[0][0]);
      expect(submission.values).toEqual(['b']);
      expect(submission.userInput).toBe('b');
      expect(view.getByText('A')).toBeInTheDocument();
      expect(view.container).not.toHaveTextContent(marker);

      view.unmount();
      onSend.mockClear();
      const restored = render(
        <ContentRender
          content={content}
          userInput={submission.userInput}
          readonly
          onSend={onSend}
        />,
      );

      expect(restored.getByText('B')).toHaveClass('select');
      expect(restored.getByText('A')).toBeInTheDocument();
      expect(onSend).not.toHaveBeenCalled();
    },
  );

  it.each([
    ['{{goal}}', false],
    ['%{{goal}}', false],
    ['{{goal}}', true],
    ['%{{goal}}', true],
  ])(
    'keeps %s visible inside an invalid image with angle destination %s',
    (marker, angle) => {
      // Backslash plus a physical LF cannot continue an image destination.
      const destination = '/diagram\\\n.png';
      const content = `![?[${marker} A | B]](${angle ? `<${destination}>` : destination})`;
      const onSend = jest.fn();
      const view = render(
        <ContentRender
          content={content}
          onSend={onSend}
        />,
      );

      expect(view.container.querySelector('img')).toBeNull();
      expect(
        view.getAllByRole('button').map(button => button.textContent),
      ).toEqual(['A', 'B']);
      fireEvent.click(view.getByText('B'));
      expect(onSend).toHaveBeenCalledTimes(1);
      expect(onSend).toHaveBeenCalledWith({
        variableName: 'goal',
        buttonText: 'B',
      });
    },
  );
});

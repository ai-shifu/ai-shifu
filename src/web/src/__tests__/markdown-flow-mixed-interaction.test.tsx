import React from 'react';
import { cleanup, fireEvent, render } from '@testing-library/react';
import { deserialize, serialize } from 'node:v8';
import { ContentRender } from 'markdown-flow-ui/renderer';
import { resolveInteractionSubmission } from '@/lib/interaction-user-input';

describe('installed MarkdownFlow mixed interaction replay', () => {
  const originalStructuredClone = globalThis.structuredClone;

  beforeAll(() => {
    globalThis.structuredClone ??= value => deserialize(serialize(value));
  });

  afterAll(() => {
    globalThis.structuredClone = originalStructuredClone;
  });

  afterEach(cleanup);

  it.each([
    ['Ready, I can paste an answer', 'ready'],
    ['Written, I can copy it', 'written'],
  ])(
    'keeps the stored value of %s out of the text field on replay and reload',
    (label, value) => {
      const content = `?[${label}//${value}|Not yet//later|...Explain]`;
      const onSend = jest.fn();
      const view = render(
        <ContentRender
          content={content}
          onSend={onSend}
        />,
      );

      fireEvent.click(view.getByText(label));
      expect(onSend).toHaveBeenCalledTimes(1);
      const submission = resolveInteractionSubmission(onSend.mock.calls[0][0]);
      expect(submission.userInput).toBe(value);
      expect(submission.values).toEqual([value]);

      view.rerender(
        <ContentRender
          content={content}
          userInput={submission.userInput}
        />,
      );
      expect(view.getByRole('textbox')).toHaveValue('');
      expect(view.getByText(label)).toHaveClass('select');

      view.unmount();
      const restored = render(
        <ContentRender
          content={content}
          userInput={submission.userInput}
        />,
      );
      expect(restored.getByRole('textbox')).toHaveValue('');
      expect(restored.getByText(label)).toHaveClass('select');
    },
  );

  it('submits and restores custom text in a mixed interaction intact', () => {
    const content = '?[Ready//ready|Not yet//later|...Explain]';
    const onSend = jest.fn();
    const answer = 'My own explanation, including a comma';
    const view = render(
      <ContentRender
        content={content}
        onSend={onSend}
      />,
    );

    fireEvent.change(view.getByRole('textbox'), {
      target: { value: answer },
    });
    fireEvent.click(view.getByRole('button', { name: 'Send' }));
    expect(onSend).toHaveBeenCalledTimes(1);
    const submission = resolveInteractionSubmission(onSend.mock.calls[0][0]);
    expect(submission.userInput).toBe(answer);

    view.unmount();
    const restored = render(
      <ContentRender
        content={content}
        userInput={submission.userInput}
      />,
    );
    expect(restored.getByRole('textbox')).toHaveValue(answer);
    expect(restored.getByText('Ready')).not.toHaveClass('select');
  });
});

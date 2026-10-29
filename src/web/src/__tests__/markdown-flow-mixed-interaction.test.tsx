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

  describe.each(['%{{answer}}', '{{answer}}'])('%s binding', binding => {
    it.each(['single', 'text', 'mixed-choice', 'mixed-text'] as const)(
      'submits and restores a named %s interaction',
      kind => {
        const hasChoices = kind !== 'text';
        const hasText = kind !== 'single';
        const usesText = kind === 'text' || kind === 'mixed-text';
        const options = [
          ...(hasChoices ? ['Visible A//a', 'Visible B//b'] : []),
          ...(hasText ? ['...Explain'] : []),
        ];
        const content = `?[${binding} ${options.join(' | ')}]`;
        const answer = usesText ? 'My answer, including a comma' : 'b';
        const onSend = jest.fn();
        const view = render(
          <ContentRender
            content={content}
            onSend={onSend}
          />,
        );

        if (usesText) {
          fireEvent.change(view.getByRole('textbox'), {
            target: { value: answer },
          });
          fireEvent.click(view.getByRole('button', { name: 'Send' }));
        } else {
          fireEvent.click(view.getByText('Visible B'));
        }
        expect(onSend).toHaveBeenCalledTimes(1);
        expect(onSend).toHaveBeenCalledWith(
          expect.objectContaining({
            variableName: 'answer',
            [usesText ? 'inputText' : 'buttonText']: answer,
          }),
        );
        const submission = resolveInteractionSubmission(
          onSend.mock.calls[0][0],
        );
        expect(submission).toEqual({ values: [answer], userInput: answer });

        const props = {
          content,
          userInput: submission.userInput,
          readonly: true,
          onSend,
        };
        view.rerender(<ContentRender {...props} />);
        view.unmount();
        const restored = render(<ContentRender {...props} />);
        if (hasText) {
          expect(restored.getByRole('textbox')).toHaveValue(
            usesText ? answer : '',
          );
          expect(restored.getByRole('textbox')).toBeDisabled();
        }
        if (hasChoices) {
          if (usesText) {
            expect(restored.getByText('Visible B')).not.toHaveClass('select');
          } else {
            expect(restored.getByText('Visible B')).toHaveClass('select');
          }
          fireEvent.click(restored.getByText('Visible A'));
        }
        expect(onSend).toHaveBeenCalledTimes(1);
      },
    );
  });

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

describe('historical structured answer defaults', () => {
  it.each([
    ['text', '?[...Answer]', [], 'First, second\nThird'],
    ['single', '?[Visible A//a,b|Visible B//c]', ['a,b'], ''],
    ['multi', '?[Visible A//a,b||Visible B//c]', ['a,b', 'c'], ''],
    [
      'mixed',
      '?[Visible A//a,b||Visible B//c||...Answer]',
      ['a,b'],
      'Custom, answer',
    ],
  ])(
    'restores %s inputs after leaving and reopening the lesson',
    (kind, content, selectedValues, inputText) => {
      const userInput = JSON.stringify({
        selectedValues,
        inputText,
        buttonText: kind === 'single' ? selectedValues[0] : '',
      });
      const onSend = jest.fn();
      const props = { content, userInput, readonly: true, onSend };
      const first = render(<ContentRender {...props} />);
      first.unmount();
      const reopened = render(<ContentRender {...props} />);
      if (content.includes('...')) {
        expect(reopened.getByRole('textbox')).toHaveValue(inputText);
      }
      if (selectedValues.includes('a,b')) {
        if (kind === 'single') {
          expect(reopened.getByText('Visible A')).toHaveClass('select');
        } else {
          expect(reopened.getAllByRole('checkbox')[0]).toBeChecked();
        }
      }
      if (selectedValues.includes('c')) {
        expect(reopened.getAllByRole('checkbox')[1]).toBeChecked();
      }
      expect(onSend).not.toHaveBeenCalled();
      reopened.unmount();
    },
  );
});

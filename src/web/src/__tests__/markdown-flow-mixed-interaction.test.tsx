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

  it.each(['', '%'])(
    'submits the exact named key with %j prefix and restores its stored answer',
    prefix => {
      const key = 'Which [path] | level//hint...?';
      const content = `?[${prefix}{{ ${key} }} Ready//ready|Not yet//later|...Explain]`;
      const onSend = jest.fn();
      const view = render(
        <ContentRender
          content={content}
          onSend={onSend}
        />,
      );

      fireEvent.click(view.getByRole('button', { name: 'Ready' }));
      expect(onSend).toHaveBeenCalledTimes(1);
      const answer = onSend.mock.calls[0][0];
      expect(answer).toEqual({ variableName: key, buttonText: 'ready' });
      expect(resolveInteractionSubmission(answer)).toEqual({
        values: ['ready'],
        userInput: 'ready',
      });

      const replayProps = {
        content,
        onSend,
        readonly: true,
        userInput: JSON.stringify(answer),
      };
      view.rerender(<ContentRender {...replayProps} />);
      expect(view.getByRole('button', { name: 'Ready' })).toHaveClass('select');
      expect(view.getByRole('textbox')).toHaveValue('');

      view.unmount();
      const restored = render(<ContentRender {...replayProps} />);
      const selected = restored.getByRole('button', {
        name: 'Ready',
      });
      expect(selected).toHaveClass('select');
      expect(selected).toBeDisabled();
      expect(restored.getByRole('textbox')).toHaveValue('');
      fireEvent.click(selected);
      expect(onSend).toHaveBeenCalledTimes(1);
    },
  );

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

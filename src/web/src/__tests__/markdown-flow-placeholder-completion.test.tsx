import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { deserialize, serialize } from 'node:v8';
import { ContentRender, MarkdownFlowInput } from 'markdown-flow-ui/renderer';
import { Slide } from 'markdown-flow-ui/slide';
import { usePlaceholderAcceptedTracking } from '@/hooks/use-placeholder-accepted-tracking';
import { resolveInteractionSubmission } from '@/lib/interaction-user-input';

const mockTrackEvent = jest.fn();
jest.mock('@/hooks/use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

const originalStructuredClone = globalThis.structuredClone;
beforeAll(() => {
  globalThis.structuredClone ??= value => deserialize(serialize(value));
});
afterAll(() => {
  globalThis.structuredClone = originalStructuredClone;
});
beforeEach(() => mockTrackEvent.mockReset());

function Question({
  content,
  onSend,
  preview = false,
}: {
  content: string;
  onSend: jest.Mock;
  preview?: boolean;
}) {
  const onPlaceholderAccepted = usePlaceholderAcceptedTracking(
    'course_read',
    !preview,
  );
  return (
    <>
      <ContentRender
        content={content}
        onSend={onSend}
        onPlaceholderAccepted={onPlaceholderAccepted}
      />
      <button type='button'>Next field</button>
    </>
  );
}

function ListeningQuestion({
  onSend,
  preview,
}: {
  onSend: jest.Mock;
  preview: boolean;
}) {
  const onPlaceholderAccepted = usePlaceholderAcceptedTracking(
    'course_listen',
    !preview,
  );
  return (
    <Slide
      playerEnabled
      elementList={[
        {
          type: 'interaction',
          sequence_number: 1,
          is_new: true,
          is_marker: true,
          is_renderable: true,
          content: '?[{{answer}}...Describe your work]',
        },
      ]}
      onPlaceholderAccepted={onPlaceholderAccepted}
      onSend={onSend}
    />
  );
}

it.each([false, true])(
  'tracks real Slide Tab completion only outside preview=%s',
  async preview => {
    const user = userEvent.setup();
    const onSend = jest.fn();
    render(
      <ListeningQuestion
        onSend={onSend}
        preview={preview}
      />,
    );
    const textarea = await screen.findByRole('textbox');
    expect(mockTrackEvent).not.toHaveBeenCalled();
    await user.click(textarea);
    await user.tab();
    expect(textarea).toHaveValue('Describe your work');
    expect(textarea).toHaveFocus();
    expect(onSend).not.toHaveBeenCalled();
    const events = preview
      ? []
      : [
          [
            'learner_interaction_placeholder_accepted',
            { surface: 'course_listen' },
          ],
        ];
    expect(mockTrackEvent.mock.calls).toEqual(events);
    await user.keyboard('{Enter}');
    expect(onSend).toHaveBeenCalledWith(
      expect.objectContaining({
        variableName: 'answer',
        inputText: 'Describe your work',
      }),
      expect.any(Object),
    );
    expect(mockTrackEvent.mock.calls).toEqual(events);
  },
);

it.each([
  ['text', '?[{{answer}}...Describe your work]'],
  ['single', '?[{{answer}}First|Second|...Describe your work]'],
  ['multi', '?[{{answer}}First||Second||...Describe your work]'],
])(
  'uses the installed package to fill, edit and submit a %s answer',
  async (kind, content) => {
    const user = userEvent.setup();
    const onSend = jest.fn();
    render(
      <Question
        content={content}
        onSend={onSend}
      />,
    );
    if (kind === 'multi') await user.click(screen.getByLabelText('First'));
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    await user.click(textarea);
    await user.tab();
    expect(textarea).toHaveValue('Describe your work');
    expect(textarea).toHaveFocus();
    expect(textarea.selectionStart).toBe(textarea.value.length);
    expect(textarea.selectionEnd).toBe(textarea.value.length);
    expect(onSend).not.toHaveBeenCalled();
    expect(mockTrackEvent.mock.calls).toEqual([
      ['learner_interaction_placeholder_accepted', { surface: 'course_read' }],
    ]);
    await user.tab();
    expect(textarea).not.toHaveFocus();
    await user.click(textarea);
    await user.clear(textarea);
    await user.type(textarea, 'My edited answer');
    await user.keyboard('{Enter}');
    const answer = resolveInteractionSubmission(onSend.mock.calls[0][0]);
    expect(answer.values).toEqual(
      kind === 'multi' ? ['First', 'My edited answer'] : ['My edited answer'],
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  },
);

it('keeps preview completion functional without analytics', async () => {
  const user = userEvent.setup();
  render(
    <Question
      content='?[...Hint]'
      preview
      onSend={jest.fn()}
    />,
  );
  await user.click(screen.getByRole('textbox'));
  await user.tab();
  expect(screen.getByRole('textbox')).toHaveValue('Hint');
  expect(mockTrackEvent).not.toHaveBeenCalled();
});

it('accepts hints in standalone previews without a completion observer', async () => {
  const user = userEvent.setup();
  const onSend = jest.fn();
  render(
    <ContentRender
      content='?[...Preview hint]'
      onSend={onSend}
    />,
  );
  const textarea = screen.getByRole('textbox');
  await user.click(textarea);
  await user.tab();
  expect(textarea).toHaveValue('Preview hint');
  expect(textarea).toHaveFocus();
  expect(onSend).not.toHaveBeenCalled();
  expect(mockTrackEvent).not.toHaveBeenCalled();
});

it('preserves ordinary follow-up Tab navigation without enabling completion', async () => {
  const user = userEvent.setup();
  const onSend = jest.fn();
  render(
    <>
      <MarkdownFlowInput
        placeholder='Enter a follow-up question'
        value=''
        onSend={onSend}
      />
      <button>Next field</button>
    </>,
  );
  const textarea = screen.getByRole('textbox');
  await user.click(textarea);
  await user.tab();
  expect(textarea).toHaveValue('');
  expect(screen.getByText('Next field')).toHaveFocus();
  expect(onSend).not.toHaveBeenCalled();
});

it.each(['throw', 'reject'])(
  'still edits and submits if tracking fails: %s',
  async failure => {
    mockTrackEvent.mockImplementation(() => {
      if (failure === 'throw') throw new Error('tracking unavailable');
      return Promise.reject(new Error('tracking unavailable'));
    });
    const onSend = jest.fn();
    render(
      <Question
        content='?[...Hint]'
        onSend={onSend}
      />,
    );
    const textarea = screen.getByRole('textbox');
    await act(async () => {
      textarea.focus();
      fireEvent.keyDown(textarea, { key: 'Tab' });
      await Promise.resolve();
    });
    expect(textarea).toHaveValue('Hint');
    fireEvent.change(textarea, { target: { value: 'Edited' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });
    expect(onSend).toHaveBeenCalledWith({
      variableName: '',
      inputText: 'Edited',
    });
  },
);

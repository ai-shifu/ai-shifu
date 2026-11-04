import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { deserialize, serialize } from 'node:v8';
import { ContentRender } from 'markdown-flow-ui/renderer';
import { Slide } from 'markdown-flow-ui/slide';
import { resolveInteractionSubmission } from '@/lib/interaction-user-input';

const originalStructuredClone = globalThis.structuredClone;
beforeAll(() => {
  globalThis.structuredClone ??= value => deserialize(serialize(value));
});
afterAll(() => {
  globalThis.structuredClone = originalStructuredClone;
});
beforeEach(() => {
  jest.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  jest.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
  jest.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
});
afterEach(() => jest.restoreAllMocks());

const cases = [
  { kind: 'single', controls: '?[%{{answer}} A//a | B//b]', values: ['b'] },
  {
    kind: 'multi',
    controls: '?[%{{answer}} A//a || B//b]',
    values: ['a', 'b'],
  },
  {
    kind: 'text',
    controls: '?[%{{answer}} ...Your response]',
    values: ['Own answer'],
  },
  {
    kind: 'mixed',
    controls: '?[%{{answer}} A//a | B//b | ...Your response]',
    values: ['Own answer'],
  },
];

it.each(cases)(
  'keeps the legacy prefixed $kind Slide interaction visible and answerable',
  async ({ kind, controls, values }) => {
    const user = userEvent.setup();
    const onSend = jest.fn();
    const content = encodePrompt('Question?') + controls;
    render(
      <Slide
        playerEnabled
        elementList={[
          {
            type: 'interaction',
            sequence_number: 1,
            is_new: true,
            is_marker: true,
            is_renderable: true,
            content,
          },
        ]}
        onSend={onSend}
      />,
    );
    expect(await screen.findByText('Question?')).toBeVisible();
    await act(async () => {
      if (kind === 'single') {
        await user.click(screen.getByText('B'));
      } else if (kind === 'multi') {
        await user.click(screen.getByLabelText('A'));
        await user.click(screen.getByLabelText('B'));
        await user.click(screen.getByRole('button', { name: 'Submit' }));
      } else {
        fireEvent.change(screen.getByRole('textbox'), {
          target: { value: 'Own answer' },
        });
        await user.click(screen.getByRole('button', { name: 'Send' }));
      }
    });
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(
      resolveInteractionSubmission(onSend.mock.calls[0][0]).values,
    ).toEqual(values);
    expect(onSend.mock.calls[0][0].variableName).toBe('answer');
    expect(onSend.mock.calls[0][1].content).toBe(content);
  },
);

it('keeps the prefixed reading controls and readonly selected answer intact for a legacy bundle', () => {
  render(
    <ContentRender
      content={encodePrompt('Question?') + '?[%{{answer}} A//a | B//b]'}
      userInput='b'
      readonly
    />,
  );
  expect(screen.getByText('Question?')).toBeVisible();
  expect(screen.getByText('B')).toHaveClass('select');
  expect(screen.getByText('B')).toBeDisabled();
  expect(screen.getByText('A')).toBeDisabled();
});

const encodePrompt = (prompt: string) =>
  Array.from(prompt)
    .map(char => `&#${char.codePointAt(0)};`)
    .join('') + '\n\n';

describe.each(['reader', 'slide'] as const)(
  'numeric entity compatibility prefix in real %s',
  surface => {
    it.each([
      ['fence', '```text\nQuestion?'],
      ['pre', '<pre>Question?'],
      ['script', '<script>Question?'],
      ['style', '<style>Question?'],
      ['interaction syntax', 'Question? ?[Trap A | Trap B]'],
      ['variable syntax', '{{key}} %{{other_key}}'],
      ['emoji', '🧑🏽‍💻 👨‍👩‍👧‍👦 🇨🇳 é'],
    ])(
      'preserves a %s prompt as text and keeps only the real controls',
      async (_kind, prompt) => {
        const user = userEvent.setup();
        const onSend = jest.fn();
        const content =
          encodePrompt(prompt) + '?[%{{answer}} Choice A//a | Choice B//b]';
        const view = render(
          surface === 'reader' ? (
            <ContentRender
              content={content}
              onSend={onSend}
            />
          ) : (
            <Slide
              playerEnabled
              elementList={[
                {
                  type: 'interaction',
                  sequence_number: 1,
                  is_new: true,
                  is_marker: true,
                  is_renderable: true,
                  content,
                },
              ]}
              onSend={onSend}
            />
          ),
        );
        const choice = await screen.findByText('Choice B');
        const body =
          surface === 'slide'
            ? (view.container.querySelector(
                '.slide-player__interaction-body',
              ) as HTMLElement)
            : view.container;
        expect(body.textContent).toContain(prompt);
        expect(within(body).getAllByRole('button')).toHaveLength(2);
        expect(body.querySelector('pre, script, style')).toBeNull();
        expect(within(body).queryByText('Trap A')).not.toBeInTheDocument();
        await act(async () => user.click(choice));
        expect(onSend).toHaveBeenCalledTimes(1);
        expect(onSend.mock.calls[0][0].variableName).toBe('answer');
        expect(
          resolveInteractionSubmission(onSend.mock.calls[0][0]).values,
        ).toEqual(['b']);
      },
    );
  },
);

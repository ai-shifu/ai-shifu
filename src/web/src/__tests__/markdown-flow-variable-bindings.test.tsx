import React from 'react';
import { cleanup, fireEvent, render } from '@testing-library/react';
import { deserialize, serialize } from 'node:v8';
import { ContentRender } from 'markdown-flow-ui/renderer';
import { createInteractionParser } from 'remark-flow';
import { resolveInteractionSubmission } from '@/lib/interaction-user-input';

const imageCases = ['{{goal}}', '%{{goal}}'].flatMap(marker =>
  [
    ['data URI', 'data:image/svg+xml;base64,PHN2Zy8+', ''],
    ['JavaScript URI', 'javascript:alert(1)', ''],
    ['VBScript URI', 'vbscript:alert(1)', ''],
    ['file URI', 'file:///diagram.svg', ''],
    ['escaped JavaScript colon', 'javascript\\:alert(1)', ''],
    ['entity JavaScript colon', 'javascript&#58;alert(1)', ''],
    [
      'remote URL',
      'https://example.com/diagram.svg',
      'https://example.com/diagram.svg',
    ],
    ['relative URL', '/diagram.svg', '/diagram.svg'],
  ].flatMap(([label, destination, expectedSrc]) =>
    ['inline', 'reference before', 'reference after'].flatMap(syntax =>
      [false, true].map(angle => {
        const resource = angle ? `<${destination}>` : destination;
        const image = `![?[${marker} A | B]]`;
        const definition = `[diagram]: ${resource}`;
        const reference = `${image}[diagram]`;
        const content =
          syntax === 'inline'
            ? `${image}(${resource})`
            : syntax === 'reference before'
              ? `${definition}\n\n${reference}`
              : `${reference}\n\n${definition}`;
        return { marker, label, expectedSrc, syntax, angle, content };
      }),
    ),
  ),
);

const referenceLabelFixtures = [
  ['escaped newline', 'course\\\nimage', 'course\\ image', true],
  ['escaped punctuation', 'course\\:image', 'course\\:image', true],
  ['different punctuation escape', 'course\\:image', 'course:image', false],
  ['nonpunctuation escape', 'course\\ximage', 'course\\ximage', true],
  ['odd trailing backslash', 'course\\', 'course\\', false],
  ['even trailing backslashes', 'course\\\\', 'course\\\\', true],
  ['backslash space', 'course\\ image', 'course\\ image', true],
  ['backslash tab', 'course\\\timage', 'course\\ image', true],
  ['backslash padded newline', 'course\\  \n\timage', 'course\\ image', true],
  ['escaped opening bracket', 'course\\[image', 'course\\[image', true],
  ['escaped closing bracket', 'course\\]image', 'course\\]image', true],
  ['unescaped opening bracket', 'course[image', 'course[image', false],
  ['whitespace only', ' \t\n ', 'unused', false],
  ['undefined label', 'course\\\nimage', 'other', false],
] as const;

const referenceLabelCases = ['{{goal}}', '%{{goal}}'].flatMap(marker =>
  referenceLabelFixtures.flatMap(
    ([label, use, definitionLabel, expectedImage]) =>
      [
        ['LF', '\n'],
        ['CRLF', '\r\n'],
        ['CR', '\r'],
      ].flatMap(([lineEnding, newline]) =>
        ['plain', 'quote', 'list'].flatMap(container =>
          ['before', 'after'].map(order => {
            const image = `![?[${marker} A | B]][${use}]`;
            const definition = `[${definitionLabel}]: /x`;
            const document =
              order === 'before'
                ? `${definition}\n\n${image}`
                : `${image}\n\n${definition}`;
            const content = document
              .split('\n')
              .map((line, index) =>
                container === 'quote'
                  ? `> ${line}`
                  : container === 'list'
                    ? `${index === 0 ? '- ' : '  '}${line}`
                    : line,
              )
              .join(newline);
            return {
              marker,
              label,
              expectedImage,
              lineEnding,
              container,
              order,
              content,
            };
          }),
        ),
      ),
  ),
);

const referenceLabelLengthCases = ['{{goal}}', '%{{goal}}'].flatMap(marker =>
  [999, 1000].flatMap(size => {
    const labels = [
      ['ordinary characters', 'a'.repeat(size), 'a'.repeat(size)],
      ...[
        ['escaped punctuation', '\\:'],
        ['nonpunctuation escapes', '\\x'],
      ].map(([name, pair]) => {
        const label = pair.repeat(Math.floor(size / 2)) + 'a'.repeat(size % 2);
        return [name, label, label];
      }),
      ...[
        ['LF', '\n'],
        ['CRLF', '\r\n'],
        ['CR', '\r'],
      ].map(([name, newline]) => [
        `${name} after backslash`,
        `${'a'.repeat(size - 502)}\\${newline}${'b'.repeat(500)}`,
        `${'a'.repeat(size - 502)}\\ ${'b'.repeat(500)}`,
      ]),
    ];
    return labels.map(([label, use, definition]) => ({
      marker,
      label: `${label} at normalized source length ${size}`,
      expectedImage: size === 999,
      lineEnding: 'label boundary',
      container: 'plain',
      order: 'after',
      content: `![?[${marker} A | B]][${use}]\n\n[${definition}]: /x`,
    }));
  }),
);

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

  it.each(imageCases)(
    'keeps $marker in a $syntax image with $label and angle destination $angle as image content',
    ({ marker, expectedSrc, content }) => {
      const onSend = jest.fn();
      const view = render(
        <ContentRender
          content={content}
          onSend={onSend}
        />,
      );

      // URL sanitization changes src, never ownership of the image's alt text.
      expect(view.getByAltText(`?[${marker} A | B]`)).toHaveAttribute(
        'src',
        expectedSrc,
      );
      expect(view.queryAllByRole('button')).toEqual([]);
      expect(onSend).not.toHaveBeenCalled();

      view.rerender(
        <ContentRender
          content={`${content}\n\n?[{{visible}} C | D]`}
          onSend={onSend}
        />,
      );
      expect(
        view.getAllByRole('button').map(button => button.textContent),
      ).toEqual(['C', 'D']);
      expect(onSend).not.toHaveBeenCalled();

      fireEvent.click(view.getByText('D'));
      expect(onSend).toHaveBeenCalledTimes(1);
      expect(onSend).toHaveBeenCalledWith({
        variableName: 'visible',
        buttonText: 'D',
      });
    },
  );

  it.each([...referenceLabelCases, ...referenceLabelLengthCases])(
    'preserves reference-label grammar for $marker: $label ($lineEnding, $container, definition $order)',
    ({ marker, content, expectedImage }) => {
      const onSend = jest.fn();
      const view = render(
        <ContentRender
          content={content}
          onSend={onSend}
        />,
      );

      expect(onSend).not.toHaveBeenCalled();
      if (expectedImage) {
        expect(view.getByAltText(`?[${marker} A | B]`)).toHaveAttribute(
          'src',
          '/x',
        );
        expect(view.queryAllByRole('button')).toEqual([]);

        view.rerender(
          <ContentRender
            content={`${content}\n\n?[{{visible}} C | D]`}
            onSend={onSend}
          />,
        );
        expect(
          view.getAllByRole('button').map(button => button.textContent),
        ).toEqual(['C', 'D']);
        fireEvent.click(view.getByText('D'));
        expect(onSend).toHaveBeenCalledWith({
          variableName: 'visible',
          buttonText: 'D',
        });
      } else {
        expect(view.container.querySelector('img')).toBeNull();
        expect(
          view.getAllByRole('button').map(button => button.textContent),
        ).toEqual(['A', 'B']);
        fireEvent.click(view.getByText('B'));
        expect(onSend).toHaveBeenCalledWith({
          variableName: 'goal',
          buttonText: 'B',
        });
      }
      expect(onSend).toHaveBeenCalledTimes(1);
    },
  );

  it.each(['{{goal}}', '%{{goal}}'])(
    'keeps %s visible when an overlong label case-folds to a valid definition',
    marker => {
      const use = `${'\\:'.repeat(499)}SS`;
      const definition = `${'\\:'.repeat(499)}ß`;
      const onSend = jest.fn();
      const view = render(
        <ContentRender
          content={`![?[${marker} A | B]][${use}]\n\n[${definition}]: /x`}
          onSend={onSend}
        />,
      );

      // Matching normalized identifiers cannot admit a 1,000-character label.
      expect(view.container.querySelector('img')).toBeNull();
      expect(
        view.getAllByRole('button').map(button => button.textContent),
      ).toEqual(['A', 'B']);
      expect(onSend).not.toHaveBeenCalled();
      fireEvent.click(view.getByText('B'));
      expect(onSend).toHaveBeenCalledTimes(1);
      expect(onSend).toHaveBeenCalledWith({
        variableName: 'goal',
        buttonText: 'B',
      });
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

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
  [
    [999, true],
    [1000, false],
  ].flatMap(([size, expectedImage]) => {
    const length = Number(size);
    const labels = [
      ['ordinary characters', 'a'.repeat(length)],
      ...[
        ['escaped punctuation', '\\:'],
        ['nonpunctuation escapes', '\\x'],
      ].map(([name, pair]) => [
        name,
        pair.repeat(Math.floor(length / 2)) + 'a'.repeat(length % 2),
      ]),
    ];
    return labels.map(([label, value]) => ({
      marker,
      label: `${label} at single-line source length ${length}`,
      expectedImage: Boolean(expectedImage),
      lineEnding: 'single-line label boundary',
      container: 'plain',
      order: 'after',
      content: `![?[${marker} A | B]][${value}]\n\n[${value}]: /x`,
    }));
  }),
);

const referenceBudgetPrefix = '\\:'.repeat(498);
const referenceBudgetSeeds = [
  [
    'multiline use SSS',
    `${referenceBudgetPrefix}\nSSS`,
    `${referenceBudgetPrefix} Sß`,
  ],
  [
    'multiline use SSSS',
    `${referenceBudgetPrefix}\nSSSS`,
    `${referenceBudgetPrefix} ßß`,
  ],
  [
    'multiline definition SSS',
    `${referenceBudgetPrefix} Sß`,
    `${referenceBudgetPrefix}\nSSS`,
  ],
  [
    'multiline definition SSSS',
    `${referenceBudgetPrefix} ßß`,
    `${referenceBudgetPrefix}\nSSSS`,
  ],
  [
    'both multiline SSS',
    `${referenceBudgetPrefix}\nSSS`,
    `${referenceBudgetPrefix}\nSSS`,
  ],
  [
    'both multiline SSSS',
    `${referenceBudgetPrefix}\nSSSS`,
    `${referenceBudgetPrefix}\nSSSS`,
  ],
  [
    'use continuation space',
    `${referenceBudgetPrefix}\n SSS`,
    `${referenceBudgetPrefix} Sß`,
  ],
  [
    'definition continuation space',
    `${referenceBudgetPrefix} Sß`,
    `${referenceBudgetPrefix}\n SSS`,
  ],
  [
    'use continuation tab',
    `${referenceBudgetPrefix}\n\tSS`,
    `${referenceBudgetPrefix} ß`,
  ],
  [
    'definition continuation tab',
    `${referenceBudgetPrefix} ß`,
    `${referenceBudgetPrefix}\n\tSS`,
  ],
  [
    'both multiple line endings',
    `${referenceBudgetPrefix}\nS\nSS`,
    `${referenceBudgetPrefix}\nS\nSS`,
  ],
  [
    'blank line in use',
    `${referenceBudgetPrefix}\n\nSSS`,
    `${referenceBudgetPrefix} Sß`,
  ],
  [
    'blank line in definition',
    `${referenceBudgetPrefix} Sß`,
    `${referenceBudgetPrefix}\n\nSSS`,
  ],
  ['leading newline in use', `\n${'a'.repeat(999)}`, 'a'.repeat(999)],
  ['trailing newline in use', `${'a'.repeat(999)}\n`, 'a'.repeat(999)],
  ['leading newline in definition', 'a'.repeat(999), `\n${'a'.repeat(999)}`],
  ['trailing newline in definition', 'a'.repeat(999), `${'a'.repeat(999)}\n`],
  ['leading space in use', ` ${'a'.repeat(999)}`, 'a'.repeat(999)],
  ['trailing space in use', `${'a'.repeat(999)} `, 'a'.repeat(999)],
  ['leading space in definition', 'a'.repeat(999), ` ${'a'.repeat(999)}`],
  ['trailing space in definition', 'a'.repeat(999), `${'a'.repeat(999)} `],
  ['astral 499', '😀'.repeat(499), '😀'.repeat(499)],
  ['astral 499 plus ASCII', `${'😀'.repeat(499)}a`, `${'😀'.repeat(499)}a`],
  ['astral 500', '😀'.repeat(500), '😀'.repeat(500)],
];
for (const length of [995, 996, 997, 998, 999]) {
  const text = 'a'.repeat(length);
  referenceBudgetSeeds.push([
    `use trailing tab after ${length}`,
    `${text}\t`,
    text,
  ]);
  referenceBudgetSeeds.push([
    `definition trailing tab after ${length}`,
    text,
    `${text}\t`,
  ]);
}

// These outcomes come from the installed renderer, including column-sensitive tabs.
const referenceBudgetImageOwners: Record<string, boolean | string[]> = {
  'multiline use SSS': true,
  'multiline use SSSS': false,
  'multiline definition SSS': true,
  'multiline definition SSSS': false,
  'both multiline SSS': true,
  'both multiline SSSS': false,
  'use continuation space': false,
  'definition continuation space': false,
  'use continuation tab': false,
  'definition continuation tab': false,
  'both multiple line endings': true,
  'blank line in use': false,
  'blank line in definition': false,
  'leading newline in use': true,
  'trailing newline in use': true,
  'leading newline in definition': true,
  'trailing newline in definition': true,
  'leading space in use': false,
  'trailing space in use': false,
  'leading space in definition': false,
  'trailing space in definition': false,
  'astral 499': true,
  'astral 499 plus ASCII': true,
  'astral 500': false,
  'use trailing tab after 995': true,
  'definition trailing tab after 995': true,
  'use trailing tab after 996': [
    '{{goal}}/plain',
    '{{goal}}/quote',
    '{{goal}}/list',
    '%{{goal}}/plain',
  ],
  'definition trailing tab after 996': true,
  'use trailing tab after 997': ['{{goal}}/plain', '%{{goal}}/plain'],
  'definition trailing tab after 997': ['{{goal}}/plain', '%{{goal}}/plain'],
  'use trailing tab after 998': ['{{goal}}/plain'],
  'definition trailing tab after 998': ['{{goal}}/plain', '%{{goal}}/plain'],
  'use trailing tab after 999': false,
  'definition trailing tab after 999': false,
};
const referenceBudgetCases = ['{{goal}}', '%{{goal}}'].flatMap(marker =>
  referenceBudgetSeeds.flatMap(([label, use, definitionLabel]) =>
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
          const observedOwners = referenceBudgetImageOwners[label];
          const expectedImage =
            typeof observedOwners === 'boolean'
              ? observedOwners
              : observedOwners.includes(`${marker}/${container}`);
          return {
            marker,
            label,
            lineEnding,
            container,
            order,
            content,
            expectedImage,
          };
        }),
      ),
    ),
  ),
);

// Observed projection pairs include both zero-residue and partial-TAB prefixes.
const tabProjectionFixtures = [
  ['quote TAB', '> ', '> ', '>\t', '>', false],
  ['quote space TAB', '> ', '> ', '> \t', '>', false],
  ['dash space TAB', '- ', '  ', '\t', '', false],
  ['dash TAB TAB', '-\t', '    ', '\t', '', true],
  ['ordered space TAB', '1. ', '   ', '\t', '', false],
  ['ordered TAB TAB', '1.\t', '    ', '\t', '', true],
  ['nested quote TAB', '> > ', '> > ', '> >\t', '> >', true],
  ['compact nested quote TAB', '>> ', '>> ', '>>\t', '>>', false],
  ['nested dash space TAB', '- - ', '    ', '\t', '', true],
  ['nested dash TAB double TAB', '-\t- ', '      ', '\t\t', '', false],
  ['ordered nested dash double TAB', '1. - ', '     ', '\t\t', '', false],
  ['quote dash TAB', '> - ', '>   ', '>\t', '>', true],
  ['dash quote TAB', '- > ', '  > ', '\t>\t', '  >', false],
  ['dash TAB quote TAB', '-\t> ', '    > ', '\t>\t', '    >', false],
  ['quote nested dash double TAB', '> - - ', '>     ', '> \t\t', '>', false],
] as const;
const tabProjectionCases = ['{{goal}}', '%{{goal}}'].flatMap(marker =>
  tabProjectionFixtures.flatMap(
    ([
      label,
      firstPrefix,
      normalPrefix,
      tabPrefix,
      blankPrefix,
      expectedImage,
    ]) =>
      ['text', 'closing'].flatMap(profile =>
        ['use', 'definition', 'both'].flatMap(role =>
          [
            ['LF', '\n'],
            ['CRLF', '\r\n'],
            ['CR', '\r'],
          ].map(([lineEnding, newline]) => {
            const start =
              profile === 'text' ? '\\:'.repeat(498) : 'a'.repeat(999);
            const tail = profile === 'text' ? 'SSS' : '';
            const single = profile === 'text' ? `${start} Sß` : start;
            const image =
              role === 'use' || role === 'both'
                ? [
                    { kind: 'normal', value: `![?[${marker} A | B]][${start}` },
                    { kind: 'label', value: `${tail}]` },
                  ]
                : [
                    {
                      kind: 'normal',
                      value: `![?[${marker} A | B]][${single}]`,
                    },
                  ];
            const definition =
              role === 'definition' || role === 'both'
                ? [
                    { kind: 'normal', value: `[${start}` },
                    { kind: 'label', value: `${tail}]: /x` },
                  ]
                : [{ kind: 'normal', value: `[${single}]: /x` }];
            const rows = [
              ...image,
              { kind: 'blank', value: '' },
              ...definition,
            ];
            const content = rows
              .map(
                (row, index) =>
                  (index === 0
                    ? firstPrefix
                    : row.kind === 'blank'
                      ? blankPrefix
                      : row.kind === 'label'
                        ? tabPrefix
                        : normalPrefix) + row.value,
              )
              .join(newline);
            return {
              marker,
              label,
              profile,
              role,
              lineEnding,
              content,
              expectedImage,
            };
          }),
        ),
      ),
  ),
);
const exactContinuationIndentCases = ['{{goal}}', '%{{goal}}'].flatMap(marker =>
  [
    ['LF', '\n'],
    ['CRLF', '\r\n'],
    ['CR', '\r'],
  ].flatMap(([lineEnding, newline]) =>
    ([1, 4] as const).map(indentation => {
      const first = 'a'.repeat(993);
      const content = `![?[${marker} A | B]][${first} image]${newline}${newline}[${first}${newline}${' '.repeat(indentation)}image]: /x`;
      return { marker, lineEnding, indentation, content };
    }),
  ),
);

// Each form's outcome is recorded from the installed renderer's title grammar.
const imageTitleFixtures = [
  ['(Diagram (draft)', 'Diagram (draft', 'Diagram (draft', 'Diagram (draft'],
  ['(Diagram (draft))', 'Diagram (draft', false, null],
  ['(Diagram (draft)))', 'Diagram (draft', false, null],
  ['(Diagram \\(draft)', 'Diagram (draft', 'Diagram (draft', 'Diagram (draft'],
  [
    '(Diagram \\(draft\\))',
    'Diagram (draft)',
    'Diagram (draft)',
    'Diagram (draft)',
  ],
  ['(Diagram \\\\(draft))', 'Diagram \\(draft', false, null],
  [
    '(Diagram \\\\\\(draft\\))',
    'Diagram \\(draft)',
    'Diagram \\(draft)',
    'Diagram \\(draft)',
  ],
  [
    '"Diagram (draft)"',
    'Diagram (draft)',
    'Diagram (draft)',
    'Diagram (draft)',
  ],
  [
    "'Diagram (draft)'",
    'Diagram (draft)',
    'Diagram (draft)',
    'Diagram (draft)',
  ],
  [
    '(Diagram &lpar;draft&rpar;)',
    'Diagram (draft)',
    'Diagram (draft)',
    'Diagram (draft)',
  ],
  [
    '(Diagram &#40;draft&#41;)',
    'Diagram (draft)',
    'Diagram (draft)',
    'Diagram (draft)',
  ],
  [
    '(Diagram &#x28;draft&#x29;)',
    'Diagram (draft)',
    'Diagram (draft)',
    'Diagram (draft)',
  ],
  ['(Diagram\n(draft))', 'Diagram\n(draft', false, null],
  [
    '(Diagram\n\\(draft\\))',
    'Diagram\n(draft)',
    'Diagram\n(draft)',
    'Diagram\n(draft)',
  ],
  [
    '"Diagram\n(draft)"',
    'Diagram\n(draft)',
    'Diagram\n(draft)',
    'Diagram\n(draft)',
  ],
  ['(Diagram (draft)\ntext)', false, 'Diagram (draft', 'Diagram (draft'],
  [
    '(Diagram\n&lpar;draft&rpar;)',
    'Diagram\n(draft)',
    'Diagram\n(draft)',
    'Diagram\n(draft)',
  ],
] as const;
const imageTitleCases = ['{{goal}}', '%{{goal}}']
  .flatMap(marker =>
    imageTitleFixtures.flatMap((fixture, titleIndex) =>
      (['inline', 'reference', 'reference-next-line'] as const).flatMap(
        (form, formIndex) =>
          [false, true].flatMap(angle =>
            [
              ['plain', '', ''],
              ['quote', '> ', '> '],
              ['quote list', '> - ', '>   '],
              ['list quote', '- > ', '  > '],
            ].flatMap(([container, opening, continuation]) =>
              [
                ['LF', '\n'],
                ['CRLF', '\r\n'],
                ['CR', '\r'],
              ].map(([lineEnding, newline]) => {
                const destination = angle ? '</x>' : '/x';
                const title = fixture[0].replaceAll('\n', `\n${continuation}`);
                const source =
                  form === 'inline'
                    ? `${opening}![?[${marker} A | B]](${destination} ${title})`
                    : `${opening}![?[${marker} A | B]][image]\n${continuation}\n${continuation}[image]: ${destination}${form === 'reference-next-line' ? `\n${continuation}` : ' '}${title}`;
                const observed = fixture[formIndex + 1];
                return {
                  marker,
                  titleIndex,
                  form,
                  angle,
                  container,
                  lineEnding,
                  content: source.replaceAll('\n', newline),
                  expectedImage: observed !== false,
                  expectedTitle: observed === false ? null : observed,
                  expectedButtons: observed === false ? ['A', 'B'] : [],
                  variableName: 'goal',
                };
              }),
            ),
          ),
      ),
    ),
  )
  .filter(
    fixture =>
      (fixture.container === 'plain' && fixture.lineEnding === 'LF') ||
      (fixture.container !== 'plain' &&
        fixture.lineEnding !== 'LF' &&
        fixture.titleIndex === 1 &&
        !fixture.angle) ||
      (['quote', 'list quote'].includes(fixture.container) &&
        fixture.titleIndex === 12 &&
        fixture.form === 'reference-next-line' &&
        fixture.angle),
  );
const imageTitleLiteralCases = ['{{goal}}', '%{{goal}}'].flatMap(marker =>
  ['inline', 'reference', 'reference-next-line'].flatMap(form =>
    [
      ['LF', '\n'],
      ['CRLF', '\r\n'],
      ['CR', '\r'],
    ].map(([lineEnding, newline]) => {
      const title = '(Diagram (draft ?[{{inside}} X | Y])';
      const image =
        form === 'inline'
          ? `![?[${marker} A | B]](/x ${title})`
          : `![?[${marker} A | B]][image]\n\n[image]: /x${form === 'reference-next-line' ? '\n' : ' '}${title}`;
      return {
        marker,
        titleIndex: 'literal marker',
        form,
        angle: false,
        container: 'plain',
        lineEnding,
        content: `${image}\n\n?[{{visible}} C | D]`.replaceAll('\n', newline),
        expectedImage: true,
        expectedTitle: 'Diagram (draft ?[{{inside}} X | Y]',
        expectedButtons: ['C', 'D'],
        variableName: 'visible',
      };
    }),
  ),
);

// Recorded host outcomes distinguish an initial definition from later paragraph flow.
const referenceParagraphFixtures = [
  ['[one]: /one', [], []],
  [
    '[one]: /one (title)',
    ['1. ', '- ', '> '],
    ['1. ', '2. ', '9) ', '- ', '> '],
  ],
  [
    '[one]: /one\n "title"',
    ['1. ', '- ', '> '],
    ['1. ', '2. ', '9) ', '- ', '> '],
  ],
  [
    '[one]: /one trailing',
    ['1. ', '- ', '> '],
    ['1. ', '2. ', '9) ', '- ', '> '],
  ],
  [
    '[one]: /one\n[two]: /two',
    ['1. ', '- ', '> '],
    ['1. ', '2. ', '9) ', '- ', '> '],
  ],
  [
    '[one]: /one\nparagraph',
    ['1. ', '- ', '> '],
    ['1. ', '2. ', '9) ', '- ', '> '],
  ],
] as const;
const referenceParagraphContainers = [
  ['', ''],
  ['> ', '> '],
  ['- ', '  '],
  ['1. ', '   '],
  ['> - ', '>   '],
  ['- > ', '  > '],
] as const;
const referenceParagraphCases = ['{{goal}}', '%{{goal}}']
  .flatMap(marker =>
    referenceParagraphFixtures.flatMap(
      ([body, adjacentImages, blankImages], bodyIndex) =>
        referenceParagraphContainers.flatMap(
          ([opening, continuation], containerIndex) =>
            [0, 1, 2, 3].flatMap(gap =>
              ['1. ', '2. ', '9) ', '- ', '> '].map(following => {
                const context =
                  opening + body.replaceAll('\n', `\n${continuation}`);
                const separator = `\n${`${continuation}\n`.repeat(gap)}${continuation}`;
                const content = `![?[${marker} A | B]][image]\n\n${context}${separator}${following}[image]: /x`;
                const accepted: readonly string[] =
                  gap === 0 ? adjacentImages : blankImages;
                return {
                  marker,
                  bodyIndex,
                  containerIndex,
                  gap,
                  following,
                  content,
                  expectedImage: accepted.includes(following),
                };
              }),
            ),
        ),
    ),
  )
  .filter(
    fixture =>
      fixture.containerIndex === 0 ||
      ([0, 1].includes(fixture.bodyIndex) &&
        fixture.gap <= 1 &&
        ['1. ', '2. ', '- '].includes(fixture.following)),
  );
const freshReferenceDefinitionCases = ['{{goal}}', '%{{goal}}'].flatMap(
  marker =>
    ['1. ', '2. ', '- ', '+ '].flatMap(following =>
      (
        [
          [0, true],
          [1, true],
          [3, true],
          [4, false],
        ] as const
      ).map(([indentation, expectedImage]) => ({
        marker,
        bodyIndex: 'fresh definition',
        containerIndex: 'plain',
        gap: 0,
        following: `${indentation} spaces ${following}`,
        expectedImage,
        content: `![?[${marker} A | B]][image]\n\n${' '.repeat(indentation)}${following}[image]: /x`,
      })),
    ),
);

// These render-run outcomes come from the published host, not a whole-document AST.
const referenceRunBarriers = [
  ['prose', 'ordinary prose'],
  ['backticks', '```\ncode\n```'],
  ['backticks js', '```js\ncode\n```'],
  ['four backticks', '````\ncode\n````'],
  ['one-space backticks', ' ```\n code\n ```'],
  ['three-space backticks', '   ```\n   code\n   ```'],
  ['four-space backticks', '    ```\n    code\n    ```'],
  ['tildes', '~~~\ncode\n~~~'],
  ['four tildes', '~~~~\ncode\n~~~~'],
  ['mermaid backticks', '```mermaid\ngraph TD; A-->B\n```'],
  ['mermaid tildes', '~~~mermaid\ngraph TD; A-->B\n~~~'],
  ['quoted backticks', '> ```\n> code\n> ```'],
  ['list backticks', '- ```\n  code\n  ```'],
  ['quote-list backticks', '> - ```\n>   code\n>   ```'],
  ['list-quote backticks', '- > ```\n  > code\n  > ```'],
  ['indented code', '    code'],
  ['inline code', '`code`'],
  ['svg', '<svg xmlns="http://www.w3.org/2000/svg"></svg>'],
  ['sandbox div', '<div>widget</div>'],
  ['sandbox section', '<section>widget</section>'],
  ['native details', '<details>native</details>'],
  ['native pre', '<pre>native</pre>'],
  ['native table', '<table><tr><td>native</td></tr></table>'],
  ['native details widget', '<details><script>0</script></details>'],
  ['ordinary span', '<span>native</span>'],
  ['unclosed backticks', '```\ncode'],
  ['unclosed tildes', '~~~\ncode'],
  ['title metadata rewind', '[Read](/x "```")\n\n```js\ncode\n```'],
] as const;
const referenceRunContainers = [
  ['plain', '', ''],
  ['quote', '> ', '> '],
  ['list', '- ', '  '],
  ['list quote', '- > ', '  > '],
] as const;
const referenceRunOutcomes: Record<string, [string | null, boolean, number]> = {
  '0|0|cross forward|none|LF': ['/x', false, 0],
  '0|0|cross backward|none|LF': ['/x', false, 0],
  '0|0|duplicate local|none|LF': ['/remote', false, 0],
  '0|0|invalid local|none|LF': ['/remote', false, 0],
  '1|0|cross forward|none|LF': [null, true, 0],
  '1|0|cross forward|before|LF': ['/x', false, 0],
  '1|0|cross forward|after|LF': ['/x', false, 0],
  '1|0|cross backward|none|LF': [null, true, 0],
  '1|0|cross backward|before|LF': ['/x', false, 0],
  '1|0|cross backward|after|LF': ['/x', false, 0],
  '1|0|same before|none|LF': ['/x', false, 0],
  '1|0|same after|none|LF': ['/x', false, 0],
  '1|0|duplicate local|none|LF': ['/local', false, 0],
  '1|0|invalid local|none|LF': [null, true, 0],
  '1|1|cross forward|none|LF': ['/x', false, 0],
  '1|2|cross forward|none|LF': [null, true, 0],
  '1|3|cross forward|none|LF': ['/x', false, 0],
  '2|0|cross forward|none|LF': [null, true, 0],
  '2|0|cross backward|none|LF': [null, true, 0],
  '3|0|cross forward|none|LF': [null, true, 0],
  '3|0|cross backward|none|LF': [null, true, 0],
  '4|0|cross forward|none|LF': [null, true, 0],
  '4|0|cross backward|none|LF': [null, true, 0],
  '5|0|cross forward|none|LF': [null, true, 0],
  '5|0|cross backward|none|LF': [null, true, 0],
  '5|1|cross forward|none|LF': ['/x', false, 0],
  '5|2|cross forward|none|LF': ['/x', false, 0],
  '5|3|cross forward|none|LF': ['/x', false, 0],
  '6|0|cross forward|none|LF': ['/x', false, 0],
  '6|0|cross backward|none|LF': ['/x', false, 0],
  '7|0|cross forward|none|LF': ['/x', false, 0],
  '7|0|cross backward|none|LF': ['/x', false, 0],
  '7|0|same before|none|LF': ['/x', false, 0],
  '7|0|same after|none|LF': ['/x', false, 0],
  '7|0|duplicate local|none|LF': ['/remote', false, 0],
  '7|0|invalid local|none|LF': ['/remote', false, 0],
  '7|1|cross forward|none|LF': ['/x', false, 0],
  '7|2|cross forward|none|LF': ['/x', false, 0],
  '7|3|cross forward|none|LF': ['/x', false, 0],
  '8|0|cross forward|none|LF': ['/x', false, 0],
  '8|0|cross backward|none|LF': ['/x', false, 0],
  '9|0|cross forward|none|LF': [null, true, 0],
  '9|0|cross backward|none|LF': [null, true, 0],
  '10|0|cross forward|none|LF': ['/x', false, 0],
  '10|0|cross backward|none|LF': ['/x', false, 0],
  '11|0|cross forward|none|LF': ['/x', false, 0],
  '11|0|cross backward|none|LF': ['/x', false, 0],
  '12|0|cross forward|none|LF': ['/x', false, 0],
  '12|0|cross backward|none|LF': [null, false, 0],
  '13|0|cross forward|none|LF': ['/x', false, 0],
  '13|0|cross backward|none|LF': ['/x', false, 0],
  '14|0|cross forward|none|LF': ['/x', false, 0],
  '14|0|cross backward|none|LF': ['/x', false, 0],
  '15|0|cross forward|none|LF': ['/x', false, 0],
  '15|0|cross backward|none|LF': ['/x', false, 0],
  '16|0|cross forward|none|LF': ['/x', false, 0],
  '16|0|cross backward|none|LF': ['/x', false, 0],
  '17|0|cross forward|none|LF': [null, true, 0],
  '17|0|cross forward|before|LF': ['/x', false, 0],
  '17|0|cross forward|after|LF': ['/x', false, 0],
  '17|0|cross backward|none|LF': [null, true, 0],
  '17|0|cross backward|before|LF': ['/x', false, 0],
  '17|0|cross backward|after|LF': ['/x', false, 0],
  '17|0|same before|none|LF': ['/x', false, 0],
  '17|0|same after|none|LF': ['/x', false, 0],
  '17|1|cross forward|none|LF': [null, true, 0],
  '17|2|cross forward|none|LF': [null, true, 0],
  '17|3|cross forward|none|LF': [null, true, 0],
  '18|0|cross forward|none|LF': [null, true, 1],
  '18|0|cross forward|before|LF': [null, true, 1],
  '18|0|cross forward|after|LF': [null, true, 1],
  '18|0|cross backward|none|LF': [null, true, 1],
  '18|0|cross backward|before|LF': [null, true, 1],
  '18|0|cross backward|after|LF': [null, true, 1],
  '18|0|same before|none|LF': ['/x', false, 1],
  '18|0|same after|none|LF': ['/x', false, 1],
  '18|0|duplicate local|none|LF': ['/local', false, 1],
  '18|0|invalid local|none|LF': [null, true, 1],
  '18|1|cross forward|none|LF': [null, true, 1],
  '18|2|cross forward|none|LF': [null, true, 1],
  '18|3|cross forward|none|LF': [null, true, 1],
  '19|0|cross forward|none|LF': [null, true, 1],
  '19|0|cross backward|none|LF': [null, true, 1],
  '20|0|cross forward|none|LF': ['/x', false, 0],
  '20|0|cross backward|none|LF': ['/x', false, 0],
  '20|0|same before|none|LF': ['/x', false, 0],
  '20|0|same after|none|LF': ['/x', false, 0],
  '20|0|duplicate local|none|LF': ['/remote', false, 0],
  '20|0|invalid local|none|LF': ['/remote', false, 0],
  '20|1|cross forward|none|LF': ['/x', false, 0],
  '20|2|cross forward|none|LF': ['/x', false, 0],
  '20|3|cross forward|none|LF': ['/x', false, 0],
  '21|0|cross forward|none|LF': ['/x', false, 0],
  '21|0|cross backward|none|LF': ['/x', false, 0],
  '22|0|cross forward|none|LF': ['/x', false, 0],
  '22|0|cross backward|none|LF': ['/x', false, 0],
  '23|0|cross forward|none|LF': [null, true, 1],
  '23|0|cross forward|before|LF': [null, true, 1],
  '23|0|cross forward|after|LF': [null, true, 1],
  '23|0|cross backward|none|LF': [null, true, 1],
  '23|0|cross backward|before|LF': [null, true, 1],
  '23|0|cross backward|after|LF': [null, true, 1],
  '24|0|cross forward|none|LF': ['/x', false, 0],
  '24|0|cross backward|none|LF': ['/x', false, 0],
  '25|0|cross forward|none|LF': [null, true, 0],
  '25|0|cross backward|none|LF': [null, false, 0],
  '26|0|cross forward|none|LF': [null, true, 0],
  '26|0|cross backward|none|LF': [null, false, 0],
  '1|0|cross forward|none|CRLF': [null, true, 0],
  '1|0|cross forward|none|CR': ['/x', false, 0],
  '1|0|cross backward|none|CRLF': [null, true, 0],
  '1|0|cross backward|none|CR': ['/x', false, 0],
  '27|0|cross forward|none|LF': [null, true, 0],
};
const referenceRunCases = ['{{goal}}', '%{{goal}}'].flatMap(marker =>
  Object.entries(referenceRunOutcomes).map(
    ([key, [expectedSrc, expectedQuestion, expectedIframes]]) => {
      const [barrierIndex, containerIndex, layout, activation, lineEnding] =
        key.split('|');
      const [barrier, block] = referenceRunBarriers[Number(barrierIndex)];
      const [container, opening, continuation] =
        referenceRunContainers[Number(containerIndex)];
      const image = `![?[${marker} A | B]][image]`;
      let document: string;
      if (layout === 'cross forward')
        document = `${image}\n\n${block}\n\n[image]: /x`;
      else if (layout === 'cross backward')
        document = `[image]: /x\n\n${block}\n\n${image}`;
      else if (layout === 'same before')
        document = `${image}\n\n[image]: /x\n\n${block}`;
      else if (layout === 'same after')
        document = `${block}\n\n${image}\n\n[image]: /x`;
      else if (layout === 'duplicate local')
        document = `[image]: /remote\n\n${block}\n\n${image}\n\n[image]: /local`;
      else
        document = `[image]: /remote\n\n${block}\n\n${image}\n\n[image]: /local invalid`;
      if (activation === 'before')
        document = `<details>activate</details>\n\n${document}`;
      else if (activation === 'after')
        document += '\n\n<details>activate</details>';
      const newline =
        lineEnding === 'CR' ? '\r' : lineEnding === 'CRLF' ? '\r\n' : '\n';
      const content = document
        .split('\n')
        .map((line, index) => (index === 0 ? opening : continuation) + line)
        .join(newline);
      return {
        marker,
        barrier,
        container,
        layout,
        activation,
        lineEnding,
        content,
        expectedSrc,
        expectedQuestion,
        expectedIframes,
      };
    },
  ),
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

  it.each([...imageTitleCases, ...imageTitleLiteralCases])(
    'uses the observed image title grammar for $marker: $titleIndex ($form, $angle, $container, $lineEnding)',
    ({
      marker,
      content,
      expectedImage,
      expectedTitle,
      expectedButtons,
      variableName,
    }) => {
      const onSend = jest.fn();
      const view = render(
        <ContentRender
          content={content}
          onSend={onSend}
        />,
      );
      if (expectedImage) {
        const image = view.getByAltText(`?[${marker} A | B]`);
        expect(image).toHaveAttribute('src', '/x');
        if (expectedTitle === null) expect(image).not.toHaveAttribute('title');
        else expect(image).toHaveAttribute('title', expectedTitle);
      } else {
        expect(view.container.querySelector('img')).toBeNull();
      }
      expect(
        view.queryAllByRole('button').map(button => button.textContent),
      ).toEqual(expectedButtons);
      expect(onSend).not.toHaveBeenCalled();
      if (expectedButtons.length) {
        const buttonText = expectedButtons[1];
        fireEvent.click(view.getByText(buttonText));
        expect(onSend).toHaveBeenCalledTimes(1);
        expect(onSend).toHaveBeenCalledWith({ variableName, buttonText });
      }
    },
  );

  it.each([...referenceParagraphCases, ...freshReferenceDefinitionCases])(
    'uses the observed reference paragraph context for $marker: $bodyIndex ($containerIndex, $gap blanks, $following)',
    ({ marker, content, expectedImage }) => {
      const onSend = jest.fn();
      const view = render(
        <ContentRender
          content={content}
          onSend={onSend}
        />,
      );
      if (expectedImage) {
        expect(view.getByAltText(`?[${marker} A | B]`)).toHaveAttribute(
          'src',
          '/x',
        );
      } else {
        expect(view.container.querySelector('img')).toBeNull();
      }
      const answerButtons = view
        .queryAllByRole('button')
        .map(button => button.textContent)
        .filter(text => text === 'A' || text === 'B');
      expect(answerButtons).toEqual(expectedImage ? [] : ['A', 'B']);
      expect(onSend).not.toHaveBeenCalled();
      if (!expectedImage) {
        fireEvent.click(view.getByRole('button', { name: 'B' }));
        expect(onSend).toHaveBeenCalledTimes(1);
        expect(onSend).toHaveBeenCalledWith({
          variableName: 'goal',
          buttonText: 'B',
        });
      }
    },
  );

  it.each(referenceRunCases)(
    'uses the observed reference render run for $marker: $barrier ($container, $layout, native $activation, $lineEnding)',
    ({
      marker,
      content,
      barrier,
      container,
      layout,
      activation,
      lineEnding,
      expectedSrc,
      expectedQuestion,
      expectedIframes,
    }) => {
      // SSR keeps widget scripts inert while exercising the real host's run selection.
      const { renderToStaticMarkup } = jest.requireActual(
        'react-dom/server.node',
      ) as typeof import('react-dom/server');
      const onSend = jest.fn();
      const view = document.createElement('div');
      view.innerHTML = renderToStaticMarkup(
        <ContentRender
          content={content}
          onSend={onSend}
        />,
      );
      const image = view.querySelector('img');
      if (expectedSrc === null) expect(image).toBeNull();
      else {
        expect(image).toHaveAttribute('src', expectedSrc);
        expect(image).toHaveAttribute('alt', `?[${marker} A | B]`);
      }
      expect(view.querySelectorAll('iframe')).toHaveLength(expectedIframes);
      const answerButtons = Array.from(view.querySelectorAll('button'))
        .map(button => button.textContent)
        .filter(text => text === 'A' || text === 'B');
      expect(answerButtons).toEqual(expectedQuestion ? ['A', 'B'] : []);
      expect(onSend).not.toHaveBeenCalled();
      if (
        (barrier === 'backticks' || barrier === 'title metadata rewind') &&
        container === 'plain' &&
        layout === 'cross forward' &&
        activation === 'none' &&
        lineEnding === 'LF'
      ) {
        const live = render(
          <ContentRender
            content={content}
            onSend={onSend}
          />,
        );
        fireEvent.click(live.getByRole('button', { name: 'B' }));
        expect(onSend).toHaveBeenCalledTimes(1);
        expect(onSend).toHaveBeenCalledWith({
          variableName: 'goal',
          buttonText: 'B',
        });
      }
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

  it.each(referenceBudgetCases)(
    'matches the observed reference budget for $marker: $label ($lineEnding, $container, definition $order)',
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
      } else {
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
      }
    },
  );

  it.each(tabProjectionCases)(
    'preserves projected TAB padding for $marker: $label ($profile, $role, $lineEnding)',
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
      } else {
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
      }
    },
  );

  it.each(exactContinuationIndentCases)(
    'preserves the observed definition indentation for $marker ($indentation spaces, $lineEnding)',
    ({ marker, content, indentation }) => {
      const onSend = jest.fn();
      const view = render(
        <ContentRender
          content={content}
          onSend={onSend}
        />,
      );
      expect(onSend).not.toHaveBeenCalled();
      if (indentation === 1) {
        expect(view.getByAltText(`?[${marker} A | B]`)).toHaveAttribute(
          'src',
          '/x',
        );
        expect(view.queryAllByRole('button')).toEqual([]);
      } else {
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
      }
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

  it.each(['{{goal}}', '%{{goal}}'])(
    'preserves the visible %s question before an HTML sandbox',
    marker => {
      // The host splits sandbox HTML before resolving Markdown references.
      const { renderToStaticMarkup } = jest.requireActual(
        'react-dom/server.node',
      ) as typeof import('react-dom/server');
      const onSend = jest.fn();
      const view = document.createElement('div');
      view.innerHTML = renderToStaticMarkup(
        <ContentRender
          content={`![?[${marker} A | B]][image]\n\n> <div>\n[image]: /x`}
          onSend={onSend}
        />,
      );
      expect(view.querySelector('img')).toBeNull();
      expect(view.querySelector('iframe')).not.toBeNull();
      expect(
        Array.from(view.querySelectorAll('button')).map(
          button => button.textContent,
        ),
      ).toEqual(['A', 'B']);
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

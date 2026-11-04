import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { deserialize, serialize } from 'node:v8';
import { Slide } from 'markdown-flow-ui/slide';

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

it('renders a real Slide prompt title as literal text without interpreting markup', async () => {
  const prompt =
    '**Question?** <img src=x onerror=alert(1)> <script>bad()</script>';
  const view = render(
    <Slide
      playerEnabled
      interactionTexts={{ title: prompt }}
      elementList={[
        {
          type: 'interaction',
          sequence_number: 1,
          is_new: true,
          is_marker: true,
          is_renderable: true,
          content: '?[A | B]',
        },
      ]}
    />,
  );
  await waitFor(() => {
    const title = view.container.querySelector(
      '.slide-player__interaction-title',
    );
    expect(title?.textContent).toBe(prompt);
    expect(title?.querySelector('strong, img, script')).toBeNull();
  });
  expect(screen.getByText('A')).toBeVisible();
  expect(screen.getByText('B')).toBeVisible();
});

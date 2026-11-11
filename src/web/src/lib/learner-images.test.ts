import {
  composeLearnerImages,
  splitInteractionImages,
  splitLearnerImages,
  serializeLearnerImageSubmission,
  toMarkdownFlowImageUserInput,
} from './learner-images';

const url = 'https://images.example/learner-images/' + 'a'.repeat(32) + '.png';

it('keeps image-only history from becoming literal empty-default JSON in the input', () => {
  const saved = splitInteractionImages(
    JSON.stringify({
      selectedValues: [],
      inputText: composeLearnerImages('', [url]),
      buttonText: '',
    }),
  );
  expect(saved).toEqual({ text: '', images: [url] });
});

it('round trips image-only and mixed answers without changing text-only input', () => {
  expect(composeLearnerImages(' plain ', [])).toBe(' plain ');
  for (const text of ['', 'Explain this diagram']) {
    const composed = composeLearnerImages(text, [url]);
    expect(splitLearnerImages(composed)).toEqual({ text, images: [url] });
    const saved = splitInteractionImages(
      JSON.stringify({ selectedValues: ['a'], inputText: composed }),
    );
    expect(JSON.parse(saved.text!)).toEqual({
      selectedValues: ['a'],
      inputText: text,
    });
    expect(saved.images).toEqual([url]);
  }
});

it('adapts native image submissions to the existing backend contract', () => {
  const native = {
    variableName: 'work',
    selectedValues: ['a'],
    inputText: 'Look here',
    images: [url],
  };
  expect(serializeLearnerImageSubmission(native)).toEqual({
    variableName: 'work',
    selectedValues: ['a'],
    inputText: `Look here\n\n![learner-image](${url})`,
  });
  expect(serializeLearnerImageSubmission({ inputText: 'Plain' })).toEqual({
    inputText: 'Plain',
  });
});

it('restores library-native image defaults from persisted marker answers', () => {
  const raw = JSON.stringify({
    selectedValues: ['a'],
    inputText: composeLearnerImages('Look here', [url]),
    buttonText: 'a',
  });
  expect(JSON.parse(toMarkdownFlowImageUserInput(raw)!)).toEqual({
    selectedValues: ['a'],
    inputText: 'Look here',
    buttonText: 'a',
    images: [url],
  });
  expect(
    JSON.parse(toMarkdownFlowImageUserInput(composeLearnerImages('', [url]))!),
  ).toEqual({ inputText: '', images: [url] });
  expect(toMarkdownFlowImageUserInput('Plain')).toBe('Plain');
});

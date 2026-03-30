import { resolveInteractionSubmission } from '@/c-utils/interaction-user-input';

describe('resolveInteractionSubmission', () => {
  it('deduplicates identical values from selectedValues and buttonText', () => {
    const result = resolveInteractionSubmission({
      variableName: 'mbti',
      selectedValues: ['ENFJ'],
      buttonText: 'ENFJ',
    });

    expect(result.values).toEqual(['ENFJ']);
    expect(result.userInput).toBe('ENFJ');
  });

  it('keeps order while trimming and removing empty values', () => {
    const result = resolveInteractionSubmission({
      variableName: 'stage',
      selectedValues: [' 脱单 ', '热恋'],
      inputText: '  ',
      buttonText: '热恋',
    });

    expect(result.values).toEqual(['脱单', '热恋']);
    expect(result.userInput).toBe('脱单, 热恋');
  });
});

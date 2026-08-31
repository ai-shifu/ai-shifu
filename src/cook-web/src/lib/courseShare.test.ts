import {
  buildCourseShareContent,
  copyCourseShareText,
  formatCourseShareMessage,
  normalizeCourseShareUrl,
  shareCourse,
  type CourseShareContent,
} from './courseShare';

const shareContent: CourseShareContent = {
  payload: {
    title: 'Practical AI',
    text: 'Learn Practical AI with me.\n\nA hands-on course.',
    url: 'https://learn.example.com/c/practical-ai',
  },
  clipboardText:
    'Learn Practical AI with me.\n\nA hands-on course.\n\nhttps://learn.example.com/c/practical-ai',
};

const createCopyDocument = (copyResult: boolean) => {
  const targetDocument = document.implementation.createHTMLDocument();
  const execCommand = jest.fn(() => copyResult);
  Object.defineProperty(targetDocument, 'execCommand', {
    configurable: true,
    value: execCommand,
  });
  return { targetDocument, execCommand };
};

describe('normalizeCourseShareUrl', () => {
  it('keeps a safe absolute course URL and removes local page state', () => {
    expect(
      normalizeCourseShareUrl(
        ' https://teacher:secret@learn.example.com/c/course-1?lessonid=lesson-2&preview=true#outline ',
      ),
    ).toBe('https://learn.example.com/c/course-1');
  });

  it('resolves a root-relative course URL against a safe origin', () => {
    expect(
      normalizeCourseShareUrl(
        '/c/course-1?lessonid=lesson-2#outline',
        'https://school.example.com/admin?tab=courses',
      ),
    ).toBe('https://school.example.com/c/course-1');
  });

  it('uses the current browser origin for root-relative course URLs', () => {
    expect(normalizeCourseShareUrl('/c/course-1?preview=true')).toBe(
      'http://localhost:3000/c/course-1',
    );
  });

  it.each([
    '',
    'not-a-url',
    'javascript:alert(1)',
    'data:text/plain,course',
    'mailto:teacher@example.com',
    'ftp://learn.example.com/c/course-1',
    '//evil.example.com/c/course-1',
    '/\\evil.example.com/c/course-1',
  ])('rejects an unsafe or invalid share URL: %s', candidate => {
    expect(normalizeCourseShareUrl(candidate)).toBeNull();
  });

  it('rejects a root-relative URL when the supplied origin is unsafe', () => {
    expect(
      normalizeCourseShareUrl('/c/course-1', 'javascript:alert(1)'),
    ).toBeNull();
  });
});

describe('course share content', () => {
  it('assembles recommendation, trimmed original description, and URL exactly', () => {
    expect(
      formatCourseShareMessage({
        recommendation: 'Learn Practical AI with me.',
        courseDescription: '  First line\nSecond line\n\nFourth line.  ',
        url: 'https://learn.example.com/c/practical-ai',
      }),
    ).toBe(
      'Learn Practical AI with me.\n\nFirst line\nSecond line\n\nFourth line.\n\nhttps://learn.example.com/c/practical-ai',
    );
  });

  it('assembles the exact Chinese recommendation, description, and URL', () => {
    expect(
      formatCourseShareMessage({
        recommendation: '推荐你来学习《AI 实战课》，体验一对一个性化学习。',
        courseDescription: '  从零开始掌握 AI。\n包含实战练习。  ',
        url: 'https://learn.example.com/c/ai-practice',
      }),
    ).toBe(
      '推荐你来学习《AI 实战课》，体验一对一个性化学习。\n\n从零开始掌握 AI。\n包含实战练习。\n\nhttps://learn.example.com/c/ai-practice',
    );
  });

  it('omits a blank description without adding an empty section', () => {
    expect(
      formatCourseShareMessage({
        recommendation: 'Learn Practical AI with me.',
        courseDescription: ' \n ',
        url: 'https://learn.example.com/c/practical-ai',
      }),
    ).toBe(
      'Learn Practical AI with me.\n\nhttps://learn.example.com/c/practical-ai',
    );
  });

  it('does not truncate the original description', () => {
    const courseDescription = '课'.repeat(500);

    const message = formatCourseShareMessage({
      recommendation: 'Recommended',
      courseDescription,
      url: 'https://learn.example.com/c/course',
    });

    expect(message).toContain(courseDescription);
    expect(message).toHaveLength(
      'Recommended'.length +
        courseDescription.length +
        'https://learn.example.com/c/course'.length +
        4,
    );
  });

  it('keeps native title, text, and URL separate from the full copied text', () => {
    expect(
      buildCourseShareContent({
        courseTitle: 'Practical AI',
        recommendation: 'Learn Practical AI with me.',
        courseDescription: '  A hands-on course.  ',
        url: 'https://learn.example.com/c/practical-ai',
      }),
    ).toEqual(shareContent);
  });
});

describe('shareCourse', () => {
  it('calls native sharing synchronously while user activation is live', async () => {
    let finishNativeShare: (() => void) | undefined;
    const share = jest.fn(
      () =>
        new Promise<void>(resolve => {
          finishNativeShare = resolve;
        }),
    );
    const canShare = jest.fn(() => true);

    const pendingResult = shareCourse(shareContent, {
      navigator: { canShare, share },
      document: null,
    });

    expect(canShare).toHaveBeenCalledWith(shareContent.payload);
    expect(share).toHaveBeenCalledWith(shareContent.payload);
    finishNativeShare?.();

    await expect(pendingResult).resolves.toEqual({
      method: 'native',
      outcome: 'success',
    });
  });

  it('reports native cancellation without copying', async () => {
    const abortError = new Error('cancelled');
    abortError.name = 'AbortError';
    const writeText = jest.fn();

    await expect(
      shareCourse(shareContent, {
        navigator: {
          share: jest.fn().mockRejectedValue(abortError),
          clipboard: { writeText },
        },
        document: null,
      }),
    ).resolves.toEqual({ method: 'native', outcome: 'cancelled' });
    expect(writeText).not.toHaveBeenCalled();
  });

  it.each([
    ['native sharing fails', jest.fn(() => true), new Error('share failed')],
    ['canShare rejects the payload', jest.fn(() => false), null],
    [
      'canShare throws',
      jest.fn(() => {
        throw new Error('canShare failed');
      }),
      null,
    ],
  ])('copies the full message when %s', async (_name, canShare, shareError) => {
    const share = shareError
      ? jest.fn().mockRejectedValue(shareError)
      : jest.fn().mockResolvedValue(undefined);
    const writeText = jest.fn().mockResolvedValue(undefined);

    await expect(
      shareCourse(shareContent, {
        navigator: {
          canShare,
          share,
          clipboard: { writeText },
        },
        document: null,
      }),
    ).resolves.toEqual({ method: 'clipboard', outcome: 'success' });
    expect(writeText).toHaveBeenCalledWith(shareContent.clipboardText);
    if (!shareError) {
      expect(share).not.toHaveBeenCalled();
    }
  });

  it('copies when the Web Share API is unavailable', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);

    await expect(
      shareCourse(shareContent, {
        navigator: { clipboard: { writeText } },
        document: null,
      }),
    ).resolves.toEqual({ method: 'clipboard', outcome: 'success' });
    expect(writeText).toHaveBeenCalledWith(shareContent.clipboardText);
  });

  it('falls through to textarea copy after Clipboard API failure', async () => {
    const writeText = jest.fn().mockRejectedValue(new Error('blocked'));
    const { targetDocument, execCommand } = createCopyDocument(true);

    await expect(
      copyCourseShareText(shareContent.clipboardText, {
        navigator: { clipboard: { writeText } },
        document: targetDocument,
      }),
    ).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith(shareContent.clipboardText);
    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(targetDocument.querySelector('textarea')).toBeNull();
  });

  it('reports total failure when neither clipboard strategy succeeds', async () => {
    const { targetDocument, execCommand } = createCopyDocument(false);

    await expect(
      shareCourse(shareContent, {
        navigator: {
          clipboard: {
            writeText: jest.fn().mockRejectedValue(new Error('blocked')),
          },
        },
        document: targetDocument,
      }),
    ).resolves.toEqual({ method: 'clipboard', outcome: 'failed' });
    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(targetDocument.querySelector('textarea')).toBeNull();
  });
});

import { act, renderHook, waitFor } from '@testing-library/react';
import { useLessonPdfPrint } from './useLessonPdfPrint';

describe('useLessonPdfPrint', () => {
  const originalTitle = 'Original page title';
  let requestAnimationFrameSpy: jest.SpyInstance;
  let printSpy: jest.Mock;

  beforeEach(() => {
    document.title = originalTitle;
    document.documentElement.classList.remove('lesson-pdf-print');
    requestAnimationFrameSpy = jest
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation(callback => {
        callback(0);
        return 1;
      });
    printSpy = jest.fn();
    Object.defineProperty(window, 'print', {
      configurable: true,
      value: printSpy,
    });
  });

  afterEach(() => {
    requestAnimationFrameSpy.mockRestore();
    document.documentElement.classList.remove('lesson-pdf-print');
    document.title = originalTitle;
  });

  it('applies the print view and PDF filename before opening the native dialog', async () => {
    const printRoot = document.createElement('div');
    const lessonImage = document.createElement('img');
    lessonImage.setAttribute('loading', 'lazy');
    printRoot.appendChild(lessonImage);
    const onError = jest.fn();
    let classAppliedDuringPrint = false;
    let titleDuringPrint = '';
    let imageLoadingDuringPrint = '';
    printSpy.mockImplementation(() => {
      classAppliedDuringPrint =
        document.documentElement.classList.contains('lesson-pdf-print');
      titleDuringPrint = document.title;
      imageLoadingDuringPrint = lessonImage.getAttribute('loading') || '';
      window.dispatchEvent(new Event('afterprint'));
    });

    const { result } = renderHook(() =>
      useLessonPdfPrint({
        printRootRef: { current: printRoot },
        lessonId: 'lesson-1',
        courseName: 'Course',
        lessonTitle: 'Lesson: One',
        onError,
      }),
    );

    await act(async () => {
      await result.current.printLessonPdf();
    });

    expect(requestAnimationFrameSpy).toHaveBeenCalledTimes(2);
    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(classAppliedDuringPrint).toBe(true);
    expect(titleDuringPrint).toBe('Course - Lesson- One');
    expect(imageLoadingDuringPrint).toBe('eager');
    expect(onError).not.toHaveBeenCalled();
    expect(document.documentElement).not.toHaveClass('lesson-pdf-print');
    expect(document.title).toBe(originalTitle);
    expect(lessonImage).toHaveAttribute('loading', 'lazy');
    expect(result.current.isPreparing).toBe(false);
  });

  it('reports an error and restores preparation state when print is unavailable', async () => {
    const onError = jest.fn();
    const { result } = renderHook(() =>
      useLessonPdfPrint({
        printRootRef: { current: null },
        lessonId: 'lesson-1',
        courseName: 'Course',
        lessonTitle: 'Lesson',
        onError,
      }),
    );

    await act(async () => {
      await result.current.printLessonPdf();
    });

    expect(printSpy).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(result.current.isPreparing).toBe(false);
  });

  it('keeps print state applied until a non-blocking dialog emits afterprint', async () => {
    const printRoot = document.createElement('div');
    const onError = jest.fn();
    const { result } = renderHook(() =>
      useLessonPdfPrint({
        printRootRef: { current: printRoot },
        lessonId: 'lesson-1',
        courseName: 'Course',
        lessonTitle: 'Lesson',
        onError,
      }),
    );
    let printPromise!: Promise<void>;

    act(() => {
      printPromise = result.current.printLessonPdf();
    });
    await waitFor(() => expect(printSpy).toHaveBeenCalledTimes(1));

    expect(document.documentElement).toHaveClass('lesson-pdf-print');
    expect(result.current.isPreparing).toBe(true);

    await act(async () => {
      window.dispatchEvent(new Event('afterprint'));
      await printPromise;
    });

    expect(document.documentElement).not.toHaveClass('lesson-pdf-print');
    expect(result.current.isPreparing).toBe(false);
    expect(onError).not.toHaveBeenCalled();
  });

  it('prints a paginatable snapshot after the sandbox finishes rendering', async () => {
    const printRoot = document.createElement('div');
    const iframeWrapper = document.createElement('div');
    iframeWrapper.className = 'content-render-iframe-sandbox';
    const iframe = document.createElement('iframe');
    iframe.className = 'content-render-iframe';
    iframeWrapper.appendChild(iframe);
    printRoot.appendChild(iframeWrapper);
    document.body.appendChild(printRoot);

    const iframeDocument = iframe.contentDocument;
    expect(iframeDocument).toBeTruthy();
    iframeDocument!.body.innerHTML = `
      <div id='root'>
        <div class='sandbox-wrapper' aria-busy='true'>
          <div class='sandbox-container'>iframe bottom marker</div>
        </div>
      </div>
    `;
    const onError = jest.fn();
    let snapshotTextDuringPrint = '';
    printSpy.mockImplementation(() => {
      const snapshot = printRoot.querySelector<HTMLElement>(
        '[data-lesson-print-iframe-snapshot="true"]',
      );
      snapshotTextDuringPrint = snapshot?.shadowRoot?.textContent ?? '';
      window.dispatchEvent(new Event('afterprint'));
    });

    const { result } = renderHook(() =>
      useLessonPdfPrint({
        printRootRef: { current: printRoot },
        lessonId: 'lesson-1',
        courseName: 'Course',
        lessonTitle: 'Lesson',
        onError,
      }),
    );
    let printPromise!: Promise<void>;

    act(() => {
      printPromise = result.current.printLessonPdf();
    });
    await waitFor(() => expect(result.current.isPreparing).toBe(true));
    expect(printSpy).not.toHaveBeenCalled();

    iframeDocument!
      .querySelector('.sandbox-wrapper')
      ?.setAttribute('aria-busy', 'false');
    await act(async () => {
      await printPromise;
    });

    expect(snapshotTextDuringPrint).toContain('iframe bottom marker');
    expect(
      printRoot.querySelector('[data-lesson-print-iframe-snapshot="true"]'),
    ).not.toBeInTheDocument();
    expect(onError).not.toHaveBeenCalled();

    printRoot.remove();
  });

  it('cancels preparation when the current lesson changes', async () => {
    const printRoot = document.createElement('div');
    const pendingImage = document.createElement('img');
    Object.defineProperty(pendingImage, 'complete', {
      configurable: true,
      value: false,
    });
    printRoot.appendChild(pendingImage);
    const onError = jest.fn();
    const { result, rerender } = renderHook(
      ({ lessonId }) =>
        useLessonPdfPrint({
          printRootRef: { current: printRoot },
          lessonId,
          courseName: 'Course',
          lessonTitle: 'Lesson',
          onError,
        }),
      { initialProps: { lessonId: 'lesson-1' } },
    );
    let printPromise!: Promise<void>;

    act(() => {
      printPromise = result.current.printLessonPdf();
    });
    await waitFor(() => expect(result.current.isPreparing).toBe(true));

    rerender({ lessonId: 'lesson-2' });
    await act(async () => {
      await printPromise;
    });

    expect(printSpy).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(result.current.isPreparing).toBe(false);
  });

  it('does not open print after the lesson page unmounts mid-preparation', async () => {
    const printRoot = document.createElement('div');
    const pendingImage = document.createElement('img');
    Object.defineProperty(pendingImage, 'complete', {
      configurable: true,
      value: false,
    });
    printRoot.appendChild(pendingImage);
    const onError = jest.fn();
    const { result, unmount } = renderHook(() =>
      useLessonPdfPrint({
        printRootRef: { current: printRoot },
        lessonId: 'lesson-1',
        courseName: 'Course',
        lessonTitle: 'Lesson',
        onError,
      }),
    );
    let printPromise!: Promise<void>;

    act(() => {
      printPromise = result.current.printLessonPdf();
    });
    unmount();
    await act(async () => {
      await printPromise;
    });

    expect(printSpy).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });
});

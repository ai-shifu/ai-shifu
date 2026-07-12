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
    const lateImage = document.createElement('img');
    lateImage.setAttribute('loading', 'lazy');
    let lateImageAppended = false;
    Object.defineProperty(lessonImage, 'decode', {
      configurable: true,
      value: jest.fn(async () => {
        if (!lateImageAppended) {
          lateImageAppended = true;
          printRoot.appendChild(lateImage);
        }
      }),
    });
    const onError = jest.fn();
    let classAppliedDuringPrint = false;
    let titleDuringPrint = '';
    let imageLoadingDuringPrint = '';
    let lateImageLoadingDuringPrint = '';
    printSpy.mockImplementation(() => {
      classAppliedDuringPrint =
        document.documentElement.classList.contains('lesson-pdf-print');
      titleDuringPrint = document.title;
      imageLoadingDuringPrint = lessonImage.getAttribute('loading') || '';
      lateImageLoadingDuringPrint = lateImage.getAttribute('loading') || '';
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
    expect(lateImageLoadingDuringPrint).toBe('eager');
    expect(onError).not.toHaveBeenCalled();
    expect(document.documentElement).not.toHaveClass('lesson-pdf-print');
    expect(document.title).toBe(originalTitle);
    expect(lessonImage).toHaveAttribute('loading', 'lazy');
    expect(lateImage).toHaveAttribute('loading', 'lazy');
    expect(result.current.isPreparing).toBe(false);
  });

  it('waits for a video poster before printing without changing its preload policy', async () => {
    const printRoot = document.createElement('div');
    const video = document.createElement('video');
    video.setAttribute('poster', '/lesson-poster.jpg');
    video.setAttribute('preload', 'none');
    printRoot.appendChild(video);
    const posterImages: HTMLImageElement[] = [];
    let posterReady = false;
    const imageSpy = jest.spyOn(window, 'Image').mockImplementation(() => {
      const image = document.createElement('img');
      Object.defineProperty(image, 'complete', {
        configurable: true,
        get: () => posterReady,
      });
      Object.defineProperty(image, 'decode', {
        configurable: true,
        value: jest.fn(async () => undefined),
      });
      posterImages.push(image);
      return image;
    });
    const onError = jest.fn();
    let preloadDuringPrint = '';
    printSpy.mockImplementation(() => {
      preloadDuringPrint = video.getAttribute('preload') || '';
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
    await waitFor(() => expect(posterImages).toHaveLength(1));

    expect(printSpy).not.toHaveBeenCalled();
    expect(video).toHaveAttribute('preload', 'none');
    posterReady = true;
    posterImages[0].dispatchEvent(new Event('load'));
    await act(async () => {
      await printPromise;
    });

    expect(imageSpy).toHaveBeenCalledTimes(2);
    expect(posterImages[0].src).toContain('/lesson-poster.jpg');
    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(preloadDuringPrint).toBe('none');
    expect(video).toHaveAttribute('preload', 'none');
    expect(onError).not.toHaveBeenCalled();
    imageSpy.mockRestore();
  });

  it('waits for a video frame and restores its preload policy after printing', async () => {
    const printRoot = document.createElement('div');
    const video = document.createElement('video');
    video.setAttribute('src', '/lesson-video.mp4');
    video.setAttribute('preload', 'none');
    let videoReadyState = 0;
    Object.defineProperty(video, 'readyState', {
      configurable: true,
      get: () => videoReadyState,
    });
    printRoot.appendChild(video);
    const onError = jest.fn();
    let preloadDuringPrint = '';
    printSpy.mockImplementation(() => {
      preloadDuringPrint = video.getAttribute('preload') || '';
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
    await waitFor(() => expect(video).toHaveAttribute('preload', 'auto'));

    expect(printSpy).not.toHaveBeenCalled();
    videoReadyState = video.HAVE_CURRENT_DATA;
    video.dispatchEvent(new Event('loadeddata'));
    await act(async () => {
      await printPromise;
    });

    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(preloadDuringPrint).toBe('auto');
    expect(video).toHaveAttribute('preload', 'none');
    expect(onError).not.toHaveBeenCalled();
  });

  it('waits for CSS background images before printing', async () => {
    const printRoot = document.createElement('div');
    const backgroundElement = document.createElement('div');
    backgroundElement.style.backgroundImage = 'url("/lesson-background.png")';
    printRoot.appendChild(backgroundElement);
    const pendingBackgroundImages: HTMLImageElement[] = [];
    const imageSpy = jest.spyOn(window, 'Image').mockImplementation(() => {
      const image = document.createElement('img');
      Object.defineProperty(image, 'complete', {
        configurable: true,
        value: false,
      });
      Object.defineProperty(image, 'decode', {
        configurable: true,
        value: jest.fn(async () => undefined),
      });
      pendingBackgroundImages.push(image);
      return image;
    });
    const onError = jest.fn();
    printSpy.mockImplementation(() => {
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
    await waitFor(() => expect(pendingBackgroundImages).toHaveLength(1));

    expect(pendingBackgroundImages[0].src).toContain('/lesson-background.png');
    expect(printSpy).not.toHaveBeenCalled();
    pendingBackgroundImages[0].dispatchEvent(new Event('load'));

    await waitFor(() => expect(pendingBackgroundImages).toHaveLength(2));
    expect(printSpy).not.toHaveBeenCalled();
    pendingBackgroundImages[1].dispatchEvent(new Event('load'));
    await act(async () => {
      await printPromise;
    });

    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
    imageSpy.mockRestore();
  });

  it('waits for source and sandbox stylesheets before freezing iframe snapshots', async () => {
    const printRoot = document.createElement('div');
    const sourceStylesheet = document.createElement('link');
    sourceStylesheet.rel = 'stylesheet';
    sourceStylesheet.href = '/lesson-source.css';
    let sourceStylesheetReady = false;
    Object.defineProperty(sourceStylesheet, 'sheet', {
      configurable: true,
      get: () => (sourceStylesheetReady ? {} : null),
    });
    const sourceLoadListenerSpy = jest.spyOn(
      sourceStylesheet,
      'addEventListener',
    );
    printRoot.appendChild(sourceStylesheet);

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
        <div class='sandbox-wrapper' aria-busy='false'>
          <div class='sandbox-container'>styled lesson content</div>
        </div>
      </div>
    `;
    const sandboxStylesheet = iframeDocument!.createElement('link');
    sandboxStylesheet.rel = 'stylesheet';
    sandboxStylesheet.href = '/lesson-sandbox.css';
    sandboxStylesheet.dataset.printStylesheet = 'sandbox';
    sandboxStylesheet.setAttribute(
      'onload',
      "document.documentElement.dataset.lessonPdfEscaped = 'true'",
    );
    let sandboxStylesheetReady = false;
    Object.defineProperty(sandboxStylesheet, 'sheet', {
      configurable: true,
      get: () => (sandboxStylesheetReady ? {} : null),
    });
    const sandboxLoadListenerSpy = jest.spyOn(
      sandboxStylesheet,
      'addEventListener',
    );
    iframeDocument!.head.appendChild(sandboxStylesheet);

    const onError = jest.fn();
    printSpy.mockImplementation(() => {
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
    await waitFor(
      () => {
        expect(sourceLoadListenerSpy).toHaveBeenCalledWith(
          'load',
          expect.any(Function),
          { once: true },
        );
        expect(sandboxLoadListenerSpy).toHaveBeenCalledWith(
          'load',
          expect.any(Function),
          { once: true },
        );
      },
      { timeout: 2000 },
    );

    sourceStylesheetReady = true;
    sourceStylesheet.dispatchEvent(new Event('load'));
    await act(async () => {
      await Promise.resolve();
    });
    expect(printSpy).not.toHaveBeenCalled();
    expect(
      printRoot.querySelector('[data-lesson-print-iframe-snapshot="true"]'),
    ).not.toBeInTheDocument();

    sandboxStylesheetReady = true;
    sandboxStylesheet.dispatchEvent(new Event('load'));
    let snapshotStylesheet: HTMLLinkElement | null = null;
    await waitFor(
      () => {
        snapshotStylesheet =
          printRoot
            .querySelector<HTMLElement>(
              '[data-lesson-print-iframe-snapshot="true"]',
            )
            ?.shadowRoot?.querySelector<HTMLLinkElement>(
              'link[data-print-stylesheet="sandbox"]',
            ) ?? null;
        expect(snapshotStylesheet).toBeTruthy();
      },
      { timeout: 2500 },
    );

    expect(printSpy).not.toHaveBeenCalled();
    expect(snapshotStylesheet).not.toHaveAttribute('onload');
    snapshotStylesheet!.dispatchEvent(new Event('load'));
    await act(async () => {
      await printPromise;
    });

    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
    expect(
      printRoot.querySelector('[data-lesson-print-iframe-snapshot="true"]'),
    ).not.toBeInTheDocument();
    printRoot.remove();
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

  it('waits for Mermaid output instead of printing its loading placeholder', async () => {
    const printRoot = document.createElement('div');
    const mermaid = document.createElement('div');
    mermaid.className = 'content-render-mermaid';
    mermaid.innerHTML = '<div>Loading Mermaid chart...</div>';
    printRoot.appendChild(mermaid);
    const onError = jest.fn();
    printSpy.mockImplementation(() => {
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
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 700));
    });

    expect(printSpy).not.toHaveBeenCalled();
    mermaid.innerHTML =
      '<div class="content-render-mermaid-inner"><svg></svg></div>';
    await act(async () => {
      await printPromise;
    });

    expect(printSpy).toHaveBeenCalledTimes(1);
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
    iframeDocument!.head.innerHTML = `
      <style>
        html, body, #root {
          font-family: system-ui, -apple-system, BlinkMacSystemFont,
            'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif;
        }
        .font-sans {
          font-family: system-ui, -apple-system, BlinkMacSystemFont,
            'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif;
        }
      </style>
    `;
    iframeDocument!.body.innerHTML = `
      <div id='root'>
        <div class='sandbox-wrapper' aria-busy='true'>
          <div class='sandbox-container font-sans'>
            中文图卡 iframe bottom marker
            <img data-print-image='initial' loading='lazy' />
            <iframe data-print-iframe='nested' loading='lazy'></iframe>
            <input data-print-field='text' />
            <input data-print-field='checked' type='checkbox' />
            <input data-print-field='file' type='file' />
            <textarea data-print-field='textarea'></textarea>
            <select data-print-field='select'>
              <option value='first'>第一项</option>
              <option value='second'>第二项</option>
            </select>
            <select data-print-field='duplicate-select'>
              <option value='shared'>重复值第一项</option>
              <option value='shared'>重复值第二项</option>
            </select>
            <select data-print-field='multi-select' multiple>
              <option value='alpha'>甲</option>
              <option value='beta'>乙</option>
              <option value='gamma'>丙</option>
            </select>
            <button type='button'>课程按钮</button>
          </div>
        </div>
      </div>
    `;
    const sourceTextInput = iframeDocument!.querySelector<HTMLInputElement>(
      '[data-print-field="text"]',
    );
    const sourceInitialImage = iframeDocument!.querySelector<HTMLImageElement>(
      '[data-print-image="initial"]',
    );
    const sourceLateImage = iframeDocument!.createElement('img');
    sourceLateImage.dataset.printImage = 'late';
    sourceLateImage.setAttribute('loading', 'lazy');
    let sourceLateImageAppended = false;
    Object.defineProperty(sourceInitialImage!, 'decode', {
      configurable: true,
      value: jest.fn(async () => {
        if (!sourceLateImageAppended) {
          sourceLateImageAppended = true;
          iframeDocument!
            .querySelector('.sandbox-container')
            ?.appendChild(sourceLateImage);
        }
      }),
    });
    const sourceNestedIframe = iframeDocument!.querySelector<HTMLIFrameElement>(
      '[data-print-iframe="nested"]',
    );
    Object.defineProperty(sourceNestedIframe!.contentDocument!, 'readyState', {
      configurable: true,
      value: 'loading',
    });
    const sourceCheckbox = iframeDocument!.querySelector<HTMLInputElement>(
      '[data-print-field="checked"]',
    );
    const sourceFileInput = iframeDocument!.querySelector<HTMLInputElement>(
      '[data-print-field="file"]',
    );
    const sourceTextarea = iframeDocument!.querySelector<HTMLTextAreaElement>(
      '[data-print-field="textarea"]',
    );
    const sourceSelect = iframeDocument!.querySelector<HTMLSelectElement>(
      '[data-print-field="select"]',
    );
    const sourceDuplicateSelect =
      iframeDocument!.querySelector<HTMLSelectElement>(
        '[data-print-field="duplicate-select"]',
      );
    const sourceMultiSelect = iframeDocument!.querySelector<HTMLSelectElement>(
      '[data-print-field="multi-select"]',
    );
    sourceTextInput!.value = '已填写答案';
    sourceCheckbox!.checked = true;
    Object.defineProperty(sourceFileInput, 'value', {
      configurable: true,
      value: 'C:\\fakepath\\资料.pdf',
    });
    sourceTextarea!.value = '补充说明';
    sourceSelect!.value = 'second';
    sourceDuplicateSelect!.selectedIndex = 1;
    sourceMultiSelect!.options[0].selected = true;
    sourceMultiSelect!.options[2].selected = true;
    const onError = jest.fn();
    let snapshotTextDuringPrint = '';
    let snapshotStylesDuringPrint = '';
    let sourceLateImageLoadingDuringPrint = '';
    let snapshotLateImageLoadingDuringPrint = '';
    let sourceNestedIframeLoadingDuringPrint = '';
    let snapshotNestedIframeLoadingDuringPrint = '';
    let snapshotFormStateDuringPrint = {};
    printSpy.mockImplementation(() => {
      const snapshot = printRoot.querySelector<HTMLElement>(
        '[data-lesson-print-iframe-snapshot="true"]',
      );
      const shadowRoot = snapshot?.shadowRoot;
      snapshotTextDuringPrint = shadowRoot?.textContent ?? '';
      snapshotStylesDuringPrint = Array.from(
        shadowRoot?.querySelectorAll('style') ?? [],
      )
        .map(style => style.textContent ?? '')
        .join('\n');
      sourceLateImageLoadingDuringPrint =
        sourceLateImage.getAttribute('loading') || '';
      snapshotLateImageLoadingDuringPrint =
        shadowRoot
          ?.querySelector<HTMLImageElement>('[data-print-image="late"]')
          ?.getAttribute('loading') || '';
      sourceNestedIframeLoadingDuringPrint =
        sourceNestedIframe?.getAttribute('loading') || '';
      snapshotNestedIframeLoadingDuringPrint =
        shadowRoot
          ?.querySelector<HTMLIFrameElement>('[data-print-iframe="nested"]')
          ?.getAttribute('loading') || '';
      snapshotFormStateDuringPrint = {
        text: shadowRoot?.querySelector<HTMLInputElement>(
          '[data-print-field="text"]',
        )?.value,
        checked: shadowRoot?.querySelector<HTMLInputElement>(
          '[data-print-field="checked"]',
        )?.checked,
        textarea: shadowRoot?.querySelector<HTMLTextAreaElement>(
          '[data-print-field="textarea"]',
        )?.value,
        select: shadowRoot?.querySelector<HTMLSelectElement>(
          '[data-print-field="select"]',
        )?.value,
        duplicateSelect: {
          selectedIndex: shadowRoot?.querySelector<HTMLSelectElement>(
            '[data-print-field="duplicate-select"]',
          )?.selectedIndex,
          label: shadowRoot?.querySelector<HTMLSelectElement>(
            '[data-print-field="duplicate-select"]',
          )?.selectedOptions[0]?.textContent,
        },
        multiSelect: Array.from(
          shadowRoot?.querySelector<HTMLSelectElement>(
            '[data-print-field="multi-select"]',
          )?.selectedOptions ?? [],
        ).map(option => option.value),
        button: shadowRoot?.querySelector('button')?.textContent,
      };
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
    await waitFor(() => expect(sourceInitialImage!.decode).toHaveBeenCalled());
    expect(printSpy).not.toHaveBeenCalled();
    sourceNestedIframe!.dispatchEvent(new Event('load'));
    let snapshotNestedIframe: HTMLIFrameElement | null = null;
    await waitFor(
      () => {
        snapshotNestedIframe =
          printRoot
            .querySelector<HTMLElement>(
              '[data-lesson-print-iframe-snapshot="true"]',
            )
            ?.shadowRoot?.querySelector<HTMLIFrameElement>(
              '[data-print-iframe="nested"]',
            ) ?? null;
        expect(snapshotNestedIframe).toBeTruthy();
      },
      { timeout: 2000 },
    );
    expect(printSpy).not.toHaveBeenCalled();
    sourceNestedIframe!.dispatchEvent(new Event('load'));
    snapshotNestedIframe!.dispatchEvent(new Event('load'));
    await act(async () => {
      await printPromise;
    });

    expect(snapshotTextDuringPrint).toContain('iframe bottom marker');
    expect(snapshotStylesDuringPrint).toContain('PingFang SC');
    expect(snapshotStylesDuringPrint).toContain('.font-sans');
    expect(sourceLateImageLoadingDuringPrint).toBe('eager');
    expect(snapshotLateImageLoadingDuringPrint).toBe('eager');
    expect(sourceNestedIframeLoadingDuringPrint).toBe('eager');
    expect(snapshotNestedIframeLoadingDuringPrint).toBe('eager');
    expect(snapshotFormStateDuringPrint).toEqual({
      text: '已填写答案',
      checked: true,
      textarea: '补充说明',
      select: 'second',
      duplicateSelect: {
        selectedIndex: 1,
        label: '重复值第二项',
      },
      multiSelect: ['alpha', 'gamma'],
      button: '课程按钮',
    });
    expect(
      printRoot.querySelector('[data-lesson-print-iframe-snapshot="true"]'),
    ).not.toBeInTheDocument();
    expect(onError).not.toHaveBeenCalled();
    expect(sourceLateImage).toHaveAttribute('loading', 'lazy');
    expect(sourceNestedIframe).toHaveAttribute('loading', 'lazy');

    printRoot.remove();
  });

  it('neutralizes active sandbox markup before attaching a print snapshot', async () => {
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
    iframeDocument!.documentElement.setAttribute(
      'onload',
      "document.documentElement.dataset.lessonPdfEscaped = 'true'",
    );
    iframeDocument!.body.setAttribute(
      'onload',
      "document.documentElement.dataset.lessonPdfEscaped = 'true'",
    );
    const activeHeadStyle = iframeDocument!.createElement('style');
    activeHeadStyle.dataset.activeStyle = 'true';
    activeHeadStyle.setAttribute(
      'onload',
      "document.documentElement.dataset.lessonPdfEscaped = 'true'",
    );
    activeHeadStyle.textContent = '.sandbox-container { color: #123456; }';
    iframeDocument!.head.appendChild(activeHeadStyle);
    iframeDocument!.body.innerHTML += `
      <div id='root'>
        <div class='sandbox-wrapper' aria-busy='false'>
          <img
            data-active-handler='true'
            onerror="document.documentElement.dataset.lessonPdfEscaped = 'true'"
          />
          <script data-active-script='true'>
            document.documentElement.dataset.lessonPdfEscaped = 'true';
          </script>
          <object data-active-object='true' data='about:blank'></object>
          <embed data-active-embed='true' src='about:blank' />
          <meta data-active-refresh='true' http-equiv='refresh' content='0' />
          <a data-unsafe-link='true' href='javascript:void(0)'>unsafe link</a>
          <input data-active-focus='true' autofocus />
          <audio data-active-audio='true' autoplay></audio>
          <iframe
            data-active-frame='true'
            sandbox='allow-scripts allow-same-origin'
            allow='camera'
            srcdoc='<p>static nested content</p><script>document.documentElement.dataset.lessonPdfEscaped = "true";</script>'
          ></iframe>
        </div>
      </div>
    `;

    const onError = jest.fn();
    printSpy.mockImplementation(() => {
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
    let snapshotFrame: HTMLIFrameElement | null = null;
    let snapshotShadowRoot: ShadowRoot | null = null;
    await waitFor(
      () => {
        snapshotShadowRoot =
          printRoot.querySelector<HTMLElement>(
            '[data-lesson-print-iframe-snapshot="true"]',
          )?.shadowRoot ?? null;
        snapshotFrame =
          snapshotShadowRoot?.querySelector<HTMLIFrameElement>(
            '[data-active-frame="true"]',
          ) ?? null;
        expect(snapshotFrame).toBeTruthy();
      },
      { timeout: 3000 },
    );

    const snapshotHandlerImage =
      snapshotShadowRoot!.querySelector<HTMLImageElement>(
        '[data-active-handler="true"]',
      );
    expect(snapshotHandlerImage).not.toHaveAttribute('onerror');
    expect(snapshotShadowRoot!.querySelector('html')).not.toHaveAttribute(
      'onload',
    );
    expect(snapshotShadowRoot!.querySelector('body')).not.toHaveAttribute(
      'onload',
    );
    expect(
      snapshotShadowRoot!.querySelector('[data-active-style="true"]'),
    ).not.toHaveAttribute('onload');
    expect(
      snapshotShadowRoot!.querySelector('[data-unsafe-link="true"]'),
    ).not.toHaveAttribute('href');
    expect(
      snapshotShadowRoot!.querySelector('[data-active-focus="true"]'),
    ).not.toHaveAttribute('autofocus');
    expect(
      snapshotShadowRoot!.querySelector('[data-active-audio="true"]'),
    ).not.toHaveAttribute('autoplay');
    expect(
      snapshotShadowRoot!.querySelector('[data-active-script]'),
    ).toBeNull();
    expect(
      snapshotShadowRoot!.querySelector('[data-active-object]'),
    ).toBeNull();
    expect(snapshotShadowRoot!.querySelector('[data-active-embed]')).toBeNull();
    expect(
      snapshotShadowRoot!.querySelector('[data-active-refresh]'),
    ).toBeNull();
    expect(snapshotFrame).toHaveAttribute('sandbox', '');
    expect(snapshotFrame).not.toHaveAttribute('allow');
    expect(snapshotFrame!.getAttribute('srcdoc')).toContain(
      'static nested content',
    );
    expect(
      iframeDocument!.querySelector('[data-active-handler="true"]'),
    ).toHaveAttribute('onerror');
    expect(
      iframeDocument!.querySelector('[data-active-frame="true"]'),
    ).toHaveAttribute('sandbox', 'allow-scripts allow-same-origin');
    snapshotHandlerImage!.dispatchEvent(new Event('error'));
    expect(document.documentElement.dataset.lessonPdfEscaped).toBeUndefined();
    expect(printSpy).not.toHaveBeenCalled();

    snapshotFrame!.dispatchEvent(new Event('load'));
    await act(async () => {
      await printPromise;
    });

    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
    printRoot.remove();
  });

  it('preserves sandbox base URLs in an imported print snapshot', async () => {
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
    const base = iframeDocument!.createElement('base');
    base.href = 'https://cdn.example/course/unit/';
    iframeDocument!.head.appendChild(base);
    const sourceStyle = iframeDocument!.createElement('style');
    sourceStyle.dataset.relativeStyle = 'true';
    sourceStyle.textContent = `
      @import "styles/theme.css";
      .unused-background { background-image: url("images/background.png"); }
    `;
    iframeDocument!.head.appendChild(sourceStyle);
    const sourceStylesheet = iframeDocument!.createElement('link');
    sourceStylesheet.rel = 'stylesheet';
    sourceStylesheet.href = 'styles/lesson.css';
    sourceStylesheet.dataset.relativeStylesheet = 'true';
    Object.defineProperty(sourceStylesheet, 'sheet', {
      configurable: true,
      value: {},
    });
    iframeDocument!.head.appendChild(sourceStylesheet);
    iframeDocument!.body.innerHTML = `
      <div id='root'>
        <div class='sandbox-wrapper' aria-busy='false'>
          <img data-relative-image='true' src='images/card.png' />
          <picture>
            <source
              data-responsive-source='true'
              srcset='images/card.png 1x, images/card@2x.png 2x'
              sizes='100vw'
            />
            <img
              data-responsive-image='true'
              src='images/fallback.png'
              srcset='images/card.png 1x, images/card@2x.png 2x'
              sizes='100vw'
            />
          </picture>
          <a data-relative-link='true' href='docs/notes.pdf'>notes</a>
          <svg>
            <defs><path id='shape' d='M0 0h1v1z' /></defs>
            <use data-fragment-reference='true' href='#shape'></use>
          </svg>
          <iframe
            data-relative-frame='true'
            src='embeds/chart.html'
          ></iframe>
          <iframe
            data-srcdoc-frame='true'
            srcdoc='<base href="../shared/" /><img src="images/nested.png" />'
          ></iframe>
        </div>
      </div>
    `;
    const sourceImages = Array.from(
      iframeDocument!.querySelectorAll<HTMLImageElement>('img'),
    );
    sourceImages.forEach(image => {
      Object.defineProperty(image, 'complete', {
        configurable: true,
        value: true,
      });
    });
    const sourceResponsiveImage =
      iframeDocument!.querySelector<HTMLImageElement>(
        '[data-responsive-image="true"]',
      );
    Object.defineProperty(sourceResponsiveImage, 'currentSrc', {
      configurable: true,
      value: 'https://cdn.example/course/unit/images/card@2x.png',
    });
    const sourceRelativeFrame =
      iframeDocument!.querySelector<HTMLIFrameElement>(
        '[data-relative-frame="true"]',
      );
    const sourceSrcdocFrame = iframeDocument!.querySelector<HTMLIFrameElement>(
      '[data-srcdoc-frame="true"]',
    );
    Object.defineProperty(sourceRelativeFrame, 'contentDocument', {
      configurable: true,
      value: null,
    });
    Object.defineProperty(sourceSrcdocFrame, 'contentDocument', {
      configurable: true,
      value: null,
    });

    const onError = jest.fn();
    printSpy.mockImplementation(() => {
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
    let snapshotShadowRoot: ShadowRoot | null = null;
    await waitFor(
      () => {
        snapshotShadowRoot =
          printRoot.querySelector<HTMLElement>(
            '[data-lesson-print-iframe-snapshot="true"]',
          )?.shadowRoot ?? null;
        expect(snapshotShadowRoot).toBeTruthy();
      },
      { timeout: 3000 },
    );

    const snapshotStylesheet =
      snapshotShadowRoot!.querySelector<HTMLLinkElement>(
        '[data-relative-stylesheet="true"]',
      );
    const snapshotStyle = snapshotShadowRoot!.querySelector<HTMLStyleElement>(
      '[data-relative-style="true"]',
    );
    const snapshotImage = snapshotShadowRoot!.querySelector<HTMLImageElement>(
      '[data-relative-image="true"]',
    );
    const snapshotResponsiveSource =
      snapshotShadowRoot!.querySelector<HTMLSourceElement>(
        '[data-responsive-source="true"]',
      );
    const snapshotResponsiveImage =
      snapshotShadowRoot!.querySelector<HTMLImageElement>(
        '[data-responsive-image="true"]',
      );
    const snapshotRelativeFrame =
      snapshotShadowRoot!.querySelector<HTMLIFrameElement>(
        '[data-relative-frame="true"]',
      );
    const snapshotSrcdocFrame =
      snapshotShadowRoot!.querySelector<HTMLIFrameElement>(
        '[data-srcdoc-frame="true"]',
      );

    expect(snapshotStylesheet).toHaveAttribute(
      'href',
      'https://cdn.example/course/unit/styles/lesson.css',
    );
    expect(snapshotStyle?.textContent).toContain(
      'url("https://cdn.example/course/unit/images/background.png")',
    );
    expect(snapshotStyle?.textContent).toContain(
      '@import "https://cdn.example/course/unit/styles/theme.css"',
    );
    expect(snapshotImage).toHaveAttribute(
      'src',
      'https://cdn.example/course/unit/images/card.png',
    );
    expect(snapshotResponsiveImage).toHaveAttribute(
      'src',
      'https://cdn.example/course/unit/images/card@2x.png',
    );
    expect(snapshotResponsiveImage).not.toHaveAttribute('srcset');
    expect(snapshotResponsiveImage).not.toHaveAttribute('sizes');
    expect(snapshotResponsiveSource).not.toHaveAttribute('srcset');
    expect(snapshotResponsiveSource).not.toHaveAttribute('sizes');
    expect(
      snapshotShadowRoot!.querySelector('[data-relative-link="true"]'),
    ).toHaveAttribute('href', 'https://cdn.example/course/unit/docs/notes.pdf');
    expect(
      snapshotShadowRoot!.querySelector('[data-fragment-reference="true"]'),
    ).toHaveAttribute('href', '#shape');
    expect(snapshotRelativeFrame).toHaveAttribute(
      'src',
      'https://cdn.example/course/unit/embeds/chart.html',
    );
    expect(snapshotRelativeFrame).toHaveAttribute('sandbox', '');
    expect(snapshotSrcdocFrame).toHaveAttribute('sandbox', '');
    expect(snapshotSrcdocFrame?.getAttribute('srcdoc')).toContain(
      '<base href="https://cdn.example/course/shared/">',
    );
    expect(sourceStylesheet).toHaveAttribute('href', 'styles/lesson.css');
    expect(sourceImages[0]).toHaveAttribute('src', 'images/card.png');
    expect(printSpy).not.toHaveBeenCalled();

    snapshotStylesheet!.dispatchEvent(new Event('load'));
    snapshotImage!.dispatchEvent(new Event('load'));
    snapshotResponsiveImage!.dispatchEvent(new Event('load'));
    snapshotRelativeFrame!.dispatchEvent(new Event('load'));
    snapshotSrcdocFrame!.dispatchEvent(new Event('load'));
    await act(async () => {
      await printPromise;
    });

    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
    printRoot.remove();
  });

  it('waits for a newly cloned cross-origin iframe before printing', async () => {
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
        <div class='sandbox-wrapper' aria-busy='false'>
          <div class='sandbox-container'>
            <iframe data-print-iframe='cross-origin' src='https://example.invalid/embed'></iframe>
          </div>
        </div>
      </div>
    `;
    const sourceNestedIframe = iframeDocument!.querySelector<HTMLIFrameElement>(
      '[data-print-iframe="cross-origin"]',
    );
    Object.defineProperty(sourceNestedIframe, 'contentDocument', {
      configurable: true,
      value: null,
    });

    const onError = jest.fn();
    printSpy.mockImplementation(() => {
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
    let snapshotNestedIframe: HTMLIFrameElement | null = null;
    await waitFor(
      () => {
        snapshotNestedIframe =
          printRoot
            .querySelector<HTMLElement>(
              '[data-lesson-print-iframe-snapshot="true"]',
            )
            ?.shadowRoot?.querySelector<HTMLIFrameElement>(
              '[data-print-iframe="cross-origin"]',
            ) ?? null;
        expect(snapshotNestedIframe).toBeTruthy();
      },
      { timeout: 3000 },
    );

    expect(printSpy).not.toHaveBeenCalled();
    snapshotNestedIframe!.dispatchEvent(new Event('load'));
    await act(async () => {
      await printPromise;
    });

    expect(printSpy).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
    printRoot.remove();
  });

  it('freezes the reading-mode viewport before scaling a sandbox snapshot', async () => {
    const printRoot = document.createElement('div');
    const iframeWrapper = document.createElement('div');
    iframeWrapper.className = 'content-render-iframe-sandbox';
    const iframe = document.createElement('iframe');
    iframe.className = 'content-render-iframe';
    Object.defineProperty(iframe, 'clientWidth', {
      configurable: true,
      value: 960,
    });
    Object.defineProperty(iframe, 'clientHeight', {
      configurable: true,
      value: 540,
    });
    iframeWrapper.appendChild(iframe);
    printRoot.appendChild(iframeWrapper);
    document.body.appendChild(printRoot);

    const iframeDocument = iframe.contentDocument;
    expect(iframeDocument).toBeTruthy();
    iframeDocument!.body.innerHTML = `
      <div id='root'>
        <div class='sandbox-wrapper' aria-busy='false'>
          <div class='sandbox-container'>
            <main data-viewport-art style='height: 100vh; display: grid;'>
              <span>left</span><span>right</span>
            </main>
          </div>
        </div>
      </div>
    `;
    iframeDocument!.body.appendChild(iframeDocument!.createElement('script'));

    const onError = jest.fn();
    let snapshotLayoutDuringPrint = {};
    printSpy.mockImplementation(() => {
      const snapshot = printRoot.querySelector<HTMLElement>(
        '[data-lesson-print-iframe-snapshot="true"]',
      );
      const shadowRoot = snapshot?.shadowRoot;
      snapshotLayoutDuringPrint = {
        sourceWidth: snapshot?.style.getPropertyValue(
          '--lesson-print-iframe-source-width',
        ),
        sourceHeight: snapshot?.style.getPropertyValue(
          '--lesson-print-iframe-source-height',
        ),
        hasStage: Boolean(
          shadowRoot?.querySelector('[data-lesson-print-iframe-stage="true"]'),
        ),
        styles: Array.from(shadowRoot?.querySelectorAll('style') ?? [])
          .map(style => style.textContent ?? '')
          .join('\n'),
        frozenHeightPriority:
          shadowRoot
            ?.querySelector<HTMLElement>('[data-viewport-art]')
            ?.style.getPropertyPriority('height') ?? '',
      };
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

    await act(async () => {
      await result.current.printLessonPdf();
    });

    expect(snapshotLayoutDuringPrint).toEqual(
      expect.objectContaining({
        sourceWidth: '960px',
        sourceHeight: '540px',
        hasStage: true,
        frozenHeightPriority: 'important',
      }),
    );
    expect((snapshotLayoutDuringPrint as { styles: string }).styles).toContain(
      'calc(100cqw / var(--lesson-print-iframe-source-width))',
    );
    expect(onError).not.toHaveBeenCalled();
    expect(
      printRoot.querySelector('[data-lesson-print-iframe-snapshot="true"]'),
    ).not.toBeInTheDocument();

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

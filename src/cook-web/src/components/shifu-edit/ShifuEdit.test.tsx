import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import ScriptEditor from './ShifuEdit';

const refreshLabel = 'refresh';
const mockMarkdownFlowEditor = jest.fn();

jest.mock('next/dynamic', () => () => {
  const MockMarkdownFlowEditor = (props: Record<string, unknown>) => {
    mockMarkdownFlowEditor(props);
    return <div data-testid='markdown-editor' />;
  };
  MockMarkdownFlowEditor.displayName = 'MockMarkdownFlowEditor';
  return MockMarkdownFlowEditor;
});

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/components/ui/Button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => (
    <button {...props}>{children}</button>
  ),
}));

jest.mock('@/components/outline-tree', () => {
  const MockOutlineTree = () => <div data-testid='outline-tree' />;
  MockOutlineTree.displayName = 'MockOutlineTree';
  return MockOutlineTree;
});
jest.mock('@/components/chapter-setting', () => () => null);
jest.mock('@/components/mdf-convert', () => ({ MdfConvertDialog: () => null }));
jest.mock('../header', () => () => null);
jest.mock('../loading', () => {
  const MockLoading = () => <div data-testid='loading' />;
  MockLoading.displayName = 'MockLoading';
  return MockLoading;
});
jest.mock('@/components/lesson-preview', () => () => null);
jest.mock('./DraftConflictDialog', () => ({
  __esModule: true,
  default: ({
    open,
    mode,
    phone,
    onRefresh,
  }: {
    open: boolean;
    mode: string;
    phone?: string;
    onRefresh?: () => void;
  }) =>
    open ? (
      <div data-testid='draft-conflict-dialog'>
        <span data-testid='draft-conflict-mode'>{mode}</span>
        <span data-testid='draft-conflict-phone'>{phone || ''}</span>
        <button onClick={onRefresh}>{refreshLabel}</button>
      </div>
    ) : null,
}));
jest.mock('@/components/ui/MarkdownFlowLink', () => () => null);
jest.mock('@/components/ui/Sheet', () => ({
  Sheet: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SheetHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SheetTitle: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
jest.mock('@/components/ui/Tabs', () => ({
  Tabs: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  TabsTrigger: ({ children }: { children: React.ReactNode }) => (
    <button>{children}</button>
  ),
}));
jest.mock('react-rnd', () => ({
  Rnd: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
jest.mock('@/hooks/useToast', () => ({ toast: jest.fn() }));
jest.mock('@/c-store', () => ({
  useEnvStore: jest.fn(() => 'https://example.com'),
}));
jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: jest.fn() }),
}));
jest.mock('@/c-utils/urlUtils', () => ({
  replaceCurrentUrlWithLessonId: jest.fn(),
}));
jest.mock('@/components/lesson-preview/usePreviewChat', () => ({
  usePreviewChat: () => ({
    items: [],
    isLoading: false,
    error: null,
    startPreview: jest.fn(),
    stopPreview: jest.fn(),
    resetPreview: jest.fn(),
    onRefresh: jest.fn(),
    onSend: jest.fn(),
    persistVariables: jest.fn(),
    onVariableChange: jest.fn(),
    variables: {},
    requestAudioForBlock: jest.fn(),
    reGenerateConfirm: jest.fn(),
  }),
}));
jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    resolvedLanguage: 'zh-CN',
    language: 'zh-CN',
    changeLanguage: jest.fn(),
  },
  normalizeLanguage: (language: string) => language,
}));

const mockLoadDraftMeta = jest.fn();
const mockLoadModels = jest.fn();
const mockLoadChapters = jest.fn();
const mockCancelAutoSaveBlocks = jest.fn();

const baseActions = {
  loadModels: mockLoadModels,
  loadChapters: mockLoadChapters,
  loadDraftMeta: mockLoadDraftMeta,
  loadMdflow: jest.fn(),
  setDraftConflict: jest.fn(),
  setAutosavePaused: jest.fn(),
  setLatestDraftMeta: jest.fn(),
  setBaseRevision: jest.fn(),
  cancelAutoSaveBlocks: mockCancelAutoSaveBlocks,
  insertPlaceholderChapter: jest.fn(),
  addRootOutline: jest.fn(),
  hideUnusedVariables: jest.fn(),
  restoreHiddenVariables: jest.fn(),
  hideVariableByKey: jest.fn(),
  saveMdflow: jest.fn(),
  previewParse: jest.fn(),
  unhideVariablesByKeys: jest.fn(),
  refreshProfileDefinitions: jest.fn(),
  syncHiddenVariablesToUsage: jest.fn(),
  setCurrentNode: jest.fn(),
  setChapters: jest.fn(),
  setBlocks: jest.fn(),
  loadMdflowHistory: jest.fn(),
  loadMdflowHistoryVersionDetail: jest.fn(),
  restoreMdflowHistory: jest.fn(),
  parseMdflow: jest.fn(),
  refreshVariableUsage: jest.fn(),
  setCurrentMdflow: jest.fn(),
  autoSaveBlocks: jest.fn(),
  getCurrentMdflow: jest.fn(() => ''),
  hasUnsavedMdflow: jest.fn(() => false),
  flushAutoSaveBlocks: jest.fn(),
  removeOutline: jest.fn(),
};

const mockShifuState = {
  mdflow: '',
  chapters: [],
  actions: baseActions,
  isLoading: false,
  variables: [],
  systemVariables: [],
  hiddenVariables: [],
  unusedVariables: [],
  hideUnusedMode: false,
  currentShifu: {
    bid: 'shifu-1',
    readonly: false,
    name: 'Course',
  },
  currentNode: {
    bid: 'chapter-1',
    id: 'chapter-1',
    depth: 0,
    name: 'Chapter 1',
    children: [],
  },
  baseRevision: null as number | null,
  latestDraftMeta: null,
  hasDraftConflict: false,
  autosavePaused: false,
};

const mockUserStoreState = {
  userInfo: {
    user_bid: 'user-1',
    user_id: 'user-1',
    language: 'zh-CN',
  },
  isInitialized: true,
  isGuest: false,
  getToken: () => 'token',
};

jest.mock('@/store', () => ({
  __esModule: true,
  useShifu: () => mockShifuState,
  useUserStore: (selector: (state: typeof mockUserStoreState) => unknown) =>
    selector(mockUserStoreState),
}));

describe('ShifuEdit draft conflict checks', () => {
  const setLessonNode = () => {
    mockShifuState.currentNode = {
      bid: 'lesson-1',
      id: 'lesson-1',
      depth: 1,
      name: 'Lesson 1',
      children: [],
    };
  };

  beforeEach(() => {
    mockMarkdownFlowEditor.mockReset();
    mockLoadDraftMeta.mockReset();
    mockLoadModels.mockReset();
    mockLoadChapters.mockReset();
    mockCancelAutoSaveBlocks.mockReset();
    Object.values(baseActions).forEach(action => {
      if (typeof action === 'function' && 'mockReset' in action) {
        (action as jest.Mock).mockReset();
      }
    });
    baseActions.getCurrentMdflow.mockReturnValue('');
    baseActions.hasUnsavedMdflow.mockReturnValue(false);
    baseActions.setCurrentMdflow.mockImplementation(value => {
      mockShifuState.mdflow = value;
    });
    mockShifuState.currentShifu = {
      bid: 'shifu-1',
      readonly: false,
      name: 'Course',
    };
    mockShifuState.currentNode = {
      bid: 'chapter-1',
      id: 'chapter-1',
      depth: 0,
      name: 'Chapter 1',
      children: [],
    };
    mockShifuState.baseRevision = null;
    mockShifuState.latestDraftMeta = null;
    mockShifuState.hasDraftConflict = false;
    mockShifuState.autosavePaused = false;
    mockShifuState.mdflow = '';
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('does not start draft conflict checks when a chapter node is selected', async () => {
    jest.useFakeTimers();
    render(<ScriptEditor id='shifu-1' />);

    await act(async () => {
      jest.advanceTimersByTime(45000);
    });

    await waitFor(() => {
      expect(mockLoadDraftMeta).not.toHaveBeenCalled();
    });
  });

  test('still loads draft meta when a lesson node is selected', async () => {
    setLessonNode();
    mockLoadDraftMeta.mockResolvedValue({ revision: 3, updated_user: null });
    baseActions.loadMdflow.mockResolvedValue(true);

    render(<ScriptEditor id='shifu-1' />);

    await waitFor(() => {
      expect(mockLoadDraftMeta).toHaveBeenCalledWith('shifu-1', 'lesson-1');
    });
  });

  test('auto-syncs latest lesson content without opening conflict dialog when there are no local edits', async () => {
    setLessonNode();
    mockShifuState.baseRevision = 1;
    baseActions.hasUnsavedMdflow.mockReturnValue(false);
    mockLoadDraftMeta.mockResolvedValue({
      revision: 2,
      updated_user: { user_bid: 'other-user', phone: '13900139000' },
    });
    baseActions.loadMdflow.mockResolvedValue(true);

    render(<ScriptEditor id='shifu-1' />);

    await waitFor(() => {
      expect(baseActions.loadMdflow).toHaveBeenCalledWith(
        'lesson-1',
        'shifu-1',
        expect.any(Object),
      );
    });
    expect(
      screen.queryByTestId('draft-conflict-dialog'),
    ).not.toBeInTheDocument();
    expect(baseActions.setBaseRevision).toHaveBeenCalledWith(2);
    expect(baseActions.setAutosavePaused).toHaveBeenCalledWith(false);
  });

  test('opens conflict dialog when remote draft is newer and local edits exist', async () => {
    setLessonNode();
    mockShifuState.baseRevision = 1;
    mockLoadDraftMeta.mockResolvedValue({ revision: 1, updated_user: null });
    baseActions.loadMdflow.mockResolvedValue(true);
    baseActions.setBaseRevision.mockClear();

    render(<ScriptEditor id='shifu-1' />);

    await waitFor(() => {
      expect(baseActions.setBaseRevision).toHaveBeenCalledWith(1);
      expect(baseActions.loadMdflow).toHaveBeenCalledTimes(1);
    });
    await act(async () => {
      await Promise.resolve();
    });

    mockLoadDraftMeta.mockReset();
    baseActions.loadMdflow.mockClear();
    baseActions.setDraftConflict.mockClear();
    baseActions.setAutosavePaused.mockClear();
    baseActions.hasUnsavedMdflow.mockReturnValue(true);
    mockLoadDraftMeta.mockResolvedValue({
      revision: 2,
      updated_user: { user_bid: 'other-user', phone: '13900139000' },
    });

    await act(async () => {
      window.dispatchEvent(new Event('focus'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(baseActions.setDraftConflict).toHaveBeenCalledWith(true);
    });
    expect(baseActions.setAutosavePaused).toHaveBeenCalledWith(true);
  });

  test('keeps local editor typing from being echoed back as controlled content', async () => {
    setLessonNode();
    mockShifuState.mdflow = 'initial content';
    const { rerender } = render(<ScriptEditor id='shifu-1' />);

    await waitFor(() => {
      expect(mockMarkdownFlowEditor).toHaveBeenCalled();
    });

    const getLatestEditorProps = () =>
      mockMarkdownFlowEditor.mock.calls.at(-1)?.[0] as {
        content?: string;
        onChange?: (value: string) => void;
      };

    expect(getLatestEditorProps().content).toBe('initial content');

    act(() => {
      getLatestEditorProps().onChange?.('initial content {{123}}');
    });

    rerender(<ScriptEditor id='shifu-1' />);

    expect(getLatestEditorProps().content).toBe('initial content');

    mockShifuState.mdflow = 'remote synced content';
    rerender(<ScriptEditor id='shifu-1' />);

    await waitFor(() => {
      expect(getLatestEditorProps().content).toBe('remote synced content');
    });
  });
});

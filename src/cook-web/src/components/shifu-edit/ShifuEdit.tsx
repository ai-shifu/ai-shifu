'use client';
import React, {
  useState,
  useEffect,
  useMemo,
  useCallback,
  useRef,
} from 'react';
import { Button } from '@/components/ui/Button';
import { Columns2, ListCollapse, Loader2, Plus, Sparkles } from 'lucide-react';
import { useShifu } from '@/store';
import { useUserStore } from '@/store';
import OutlineTree from '@/components/outline-tree';
import ChapterSettingsDialog from '@/components/chapter-setting';
import Header from '../header';
// import MarkdownFlowEditor from '../../../../../../markdown-flow-ui/src/components/MarkdownFlowEditor';
import { UploadProps, MarkdownFlowEditor, EditMode } from 'markdown-flow-ui';
import 'markdown-flow-ui/dist/markdown-flow-ui.css';
import { cn } from '@/lib/utils';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import './shifuEdit.scss';
import Loading from '../loading';
import { useTranslation } from 'react-i18next';
import i18n, { normalizeLanguage } from '@/i18n';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import LessonPreview from '@/components/lesson-preview';
import { usePreviewChat } from '@/components/lesson-preview/usePreviewChat';
import { Rnd } from 'react-rnd';
import { useTracking } from '@/c-common/hooks/useTracking';
import { LessonCreationSettings } from '@/types/shifu';

const OUTLINE_DEFAULT_WIDTH = 256;
const OUTLINE_COLLAPSED_WIDTH = 60;
const OUTLINE_STORAGE_KEY = 'shifu-outline-panel-width';

const VARIABLE_NAME_REGEXP = /\{\{([\p{L}\p{N}_]+)\}\}/gu;

// Collect variable names that truly exist in current markdown content
const extractVariableNames = (text?: string | null) => {
  if (!text) {
    return [];
  }
  const collected = new Set<string>();
  let match: RegExpExecArray | null;
  while ((match = VARIABLE_NAME_REGEXP.exec(text)) !== null) {
    if (match[1]) {
      collected.add(match[1]);
    }
    if (VARIABLE_NAME_REGEXP.lastIndex === match.index) {
      VARIABLE_NAME_REGEXP.lastIndex += 1;
    }
  }
  VARIABLE_NAME_REGEXP.lastIndex = 0;
  return Array.from(collected);
};

const ScriptEditor = ({ id }: { id: string }) => {
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const profile = useUserStore(state => state.userInfo);
  const [foldOutlineTree, setFoldOutlineTree] = useState(false);
  const [outlineWidth, setOutlineWidth] = useState(OUTLINE_DEFAULT_WIDTH);
  const previousOutlineWidthRef = useRef(OUTLINE_DEFAULT_WIDTH);
  const [editMode, setEditMode] = useState<EditMode>('quickEdit' as EditMode);
  const [isPreviewPanelOpen, setIsPreviewPanelOpen] = useState(false);
  const [isPreviewPreparing, setIsPreviewPreparing] = useState(false);
  const [addChapterDialogOpen, setAddChapterDialogOpen] = useState(false);
  const [recentVariables, setRecentVariables] = useState<string[]>([]);
  const seenVariableNamesRef = useRef<Set<string>>(new Set());
  const {
    mdflow,
    chapters,
    actions,
    isLoading,
    variables,
    systemVariables,
    currentShifu,
    currentNode,
  } = useShifu();

  const {
    items: previewItems,
    isLoading: previewLoading,
    error: previewError,
    startPreview,
    stopPreview,
    resetPreview,
    onRefresh,
    onSend,
    persistVariables,
    onVariableChange,
    variables: previewVariables,
    reGenerateConfirm,
  } = usePreviewChat();
  const editModeOptions = useMemo(
    () => [
      {
        label: t('module.shifu.creationArea.modeText'),
        value: 'quickEdit' as EditMode,
      },
      {
        label: t('module.shifu.creationArea.modeCode'),
        value: 'codeEdit' as EditMode,
      },
    ],
    [t],
  );

  useEffect(() => {
    if (profile && profile.language) {
      const next = normalizeLanguage(profile.language);
      if ((i18n.resolvedLanguage ?? i18n.language) !== next) {
        i18n.changeLanguage(next);
      }
    }
  }, [profile]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const storedWidth = window.localStorage.getItem(OUTLINE_STORAGE_KEY);
    const parsedWidth = storedWidth ? Number.parseInt(storedWidth, 10) : NaN;
    if (!Number.isNaN(parsedWidth) && parsedWidth >= OUTLINE_DEFAULT_WIDTH) {
      setOutlineWidth(parsedWidth);
      previousOutlineWidthRef.current = parsedWidth;
    }
  }, []);

  useEffect(() => {
    const baseTitle = t('common.core.adminTitle');
    const suffix = currentShifu?.name ? ` - ${currentShifu.name}` : '';
    document.title = `${baseTitle}${suffix}`;
  }, [t, currentShifu?.name]);

  const token = useUserStore(state => state.getToken());
  const baseURL = useEnvStore((state: EnvStoreState) => state.baseURL);

  useEffect(() => {
    return () => {
      stopPreview();
      resetPreview();
    };
  }, [resetPreview, stopPreview]);

  useEffect(() => {
    if (!currentNode?.bid) {
      return;
    }
    stopPreview();
    resetPreview();
  }, [currentNode?.bid, resetPreview, stopPreview]);

  const handleAddChapterClick = () => {
    if (currentShifu?.readonly) {
      return;
    }
    actions.insertPlaceholderChapter();
    // setAddChapterDialogOpen(true);
  };

  const handleAddChapterConfirm = async (settings: LessonCreationSettings) => {
    try {
      await actions.addRootOutline(settings);
      setAddChapterDialogOpen(false);
    } catch (error) {
      console.error(error);
    }
  };

  useEffect(() => {
    actions.loadModels();
    if (id) {
      actions.loadChapters(id);
    }
  }, [id]);

  const handleTogglePreviewPanel = () => {
    setIsPreviewPanelOpen(prev => {
      const next = !prev;
      if (!next) {
        stopPreview();
        resetPreview();
      }
      return next;
    });
  };

  const handleChapterSelect = useCallback(() => {
    if (!isPreviewPanelOpen) {
      return;
    }
    setIsPreviewPanelOpen(false);
    stopPreview();
    resetPreview();
  }, [isPreviewPanelOpen, stopPreview, resetPreview]);

  const handlePreview = async () => {
    if (!canPreview || !currentShifu?.bid || !currentNode?.bid) {
      return;
    }
    trackEvent('creator_lesson_preview_click', {
      shifu_bid: currentShifu.bid,
      outline_bid: currentNode.bid,
    });
    setIsPreviewPanelOpen(true);
    setIsPreviewPreparing(true);
    resetPreview();

    try {
      if (!currentShifu?.readonly) {
        await actions.saveMdflow({
          shifu_bid: currentShifu.bid,
          outline_bid: currentNode.bid,
          data: mdflow,
        });
      }
      const {
        variables: parsedVariablesMap,
        blocksCount,
        systemVariableKeys,
      } = await actions.previewParse(mdflow, currentShifu.bid, currentNode.bid);
      const previewVariablesMap = {
        ...parsedVariablesMap,
        ...previewVariables,
      };
      persistVariables({
        shifuBid: currentShifu.bid,
        systemVariableKeys,
        variables: previewVariablesMap,
      });
      void startPreview({
        shifuBid: currentShifu.bid,
        outlineBid: currentNode.bid,
        mdflow,
        variables: previewVariablesMap,
        max_block_count: blocksCount,
        systemVariableKeys,
      });
    } catch (error) {
      console.error(error);
    } finally {
      setIsPreviewPreparing(false);
    }
  };

  const mdflowVariableNames = useMemo(
    () => extractVariableNames(mdflow),
    [mdflow],
  );
  useEffect(() => {
    const previousSeen = seenVariableNamesRef.current;
    const currentSet = new Set<string>();
    const newNames: string[] = [];
    mdflowVariableNames.forEach(name => {
      if (!name) {
        return;
      }
      currentSet.add(name);
      if (!previousSeen.has(name)) {
        newNames.push(name);
      }
    });
    seenVariableNamesRef.current = currentSet;
    const currentNamesSet = new Set(mdflowVariableNames);
    if (!newNames.length) {
      setRecentVariables(prev =>
        prev.filter(name => currentNamesSet.has(name)),
      );
      return;
    }
    setRecentVariables(prev => {
      const filteredPrev = prev.filter(
        name => !newNames.includes(name) && currentNamesSet.has(name),
      );
      return [...newNames, ...filteredPrev];
    });
  }, [mdflowVariableNames]);

  const variablesList = useMemo(() => {
    const merged = new Map<string, { name: string }>();
    // Prioritize freshly added variables, then actual markdown ones, then persisted ones
    [...recentVariables, ...mdflowVariableNames, ...variables].forEach(
      variableName => {
        if (!variableName) {
          return;
        }
        if (!merged.has(variableName)) {
          merged.set(variableName, { name: variableName });
        }
      },
    );
    return Array.from(merged.values());
  }, [recentVariables, mdflowVariableNames, variables]);

  const systemVariablesList = useMemo(() => {
    return systemVariables.map((variable: Record<string, string>) => ({
      name: variable.name,
      label: variable.label,
    }));
  }, [systemVariables]);

  const variableOrder = useMemo(() => {
    return [
      ...systemVariablesList.map(variable => variable.name),
      ...variablesList.map(variable => variable.name),
    ];
  }, [systemVariablesList, variablesList]);

  const onChangeMdflow = (value: string) => {
    actions.setCurrentMdflow(value);
    // Pass snapshot so autosave persists pre-switch content + chapter id
    actions.autoSaveBlocks({
      shifu_bid: currentShifu?.bid || '',
      outline_bid: currentNode?.bid || '',
      data: value,
    });
  };

  const uploadProps: UploadProps = useMemo(() => {
    const endpoint = baseURL || window.location.origin;
    return {
      action: `${endpoint}/api/shifu/upfile`,
      headers: {
        Authorization: `Bearer ${token}`,
        Token: token,
      },
    };
  }, [token, baseURL]);

  const canPreview = Boolean(
    currentNode?.depth && currentNode.depth > 0 && currentShifu?.bid,
  );

  const previewToggleLabel = isPreviewPanelOpen
    ? t('module.shifu.previewArea.close')
    : t('module.shifu.previewArea.open');

  const previewDisabledReason = t('module.shifu.previewArea.disabled');

  const persistOutlineWidth = useCallback((width: number) => {
    if (typeof window === 'undefined') {
      return;
    }
    const normalizedWidth = Math.max(OUTLINE_DEFAULT_WIDTH, Math.round(width));
    window.localStorage.setItem(
      OUTLINE_STORAGE_KEY,
      normalizedWidth.toString(),
    );
  }, []);

  const updateOutlineWidthFromElement = useCallback((element: HTMLElement) => {
    const width = Math.round(element.getBoundingClientRect().width);
    const normalizedWidth = Math.max(OUTLINE_DEFAULT_WIDTH, width);
    setOutlineWidth(normalizedWidth);
    return normalizedWidth;
  }, []);

  const handleOutlineResize = useCallback(
    (_event: unknown, _direction: unknown, ref: HTMLElement) => {
      updateOutlineWidthFromElement(ref);
    },
    [updateOutlineWidthFromElement],
  );

  const handleOutlineResizeStop = useCallback(
    (_event: unknown, _direction: unknown, ref: HTMLElement) => {
      const width = updateOutlineWidthFromElement(ref);
      previousOutlineWidthRef.current = width;
      persistOutlineWidth(width);
    },
    [persistOutlineWidth, updateOutlineWidthFromElement],
  );

  // Toggle outline tree collapse/expand
  const toggle = () => {
    setFoldOutlineTree(prev => {
      const next = !prev;
      if (next) {
        previousOutlineWidthRef.current =
          outlineWidth > OUTLINE_COLLAPSED_WIDTH
            ? outlineWidth
            : OUTLINE_DEFAULT_WIDTH;
        setOutlineWidth(OUTLINE_COLLAPSED_WIDTH);
      } else {
        const restoredWidth =
          previousOutlineWidthRef.current > OUTLINE_COLLAPSED_WIDTH
            ? previousOutlineWidthRef.current
            : OUTLINE_DEFAULT_WIDTH;
        setOutlineWidth(restoredWidth);
      }
      return next;
    });
  };

  return (
    <div className='flex flex-col h-screen bg-gray-50'>
      <Header />
      <div className='flex flex-1 overflow-hidden'>
        <Rnd
          id='outline-panel'
          disableDragging
          enableResizing={{
            bottom: false,
            bottomLeft: false,
            bottomRight: false,
            left: false,
            right: !foldOutlineTree,
            top: false,
            topLeft: false,
            topRight: false,
          }}
          size={{
            width: `${outlineWidth}px`,
            height: '100%',
          }}
          minWidth={`${
            foldOutlineTree ? OUTLINE_COLLAPSED_WIDTH : OUTLINE_DEFAULT_WIDTH
          }px`}
          onResize={handleOutlineResize}
          onResizeStop={handleOutlineResizeStop}
          className={cn(
            'bg-white h-full transition-[width] duration-200 border-r flex-shrink-0 overflow-hidden',
          )}
          style={{ position: 'relative' }}
        >
          <div className='p-4 flex flex-col h-full'>
            <div className='flex items-center justify-between gap-3'>
              <div
                onClick={toggle}
                className='rounded border bg-white p-1 cursor-pointer text-sm hover:bg-gray-200'
              >
                <ListCollapse className='h-5 w-5' />
              </div>
              {!foldOutlineTree && (
                <Button
                  variant='outline'
                  className='h-8 bottom-0 left-4 flex-1'
                  size='sm'
                  disabled={currentShifu?.readonly}
                  onClick={handleAddChapterClick}
                >
                  <Plus />
                  {t('module.shifu.newChapter')}
                </Button>
              )}
            </div>

            {!foldOutlineTree && (
              <div className='mt-4 flex-1 min-h-0 overflow-y-auto overflow-x-hidden pb-10'>
                <ol className='text-sm'>
                  <OutlineTree
                    items={chapters}
                    onChange={newChapters => {
                      actions.setChapters([...newChapters]);
                    }}
                    onChapterSelect={handleChapterSelect}
                  />
                </ol>
              </div>
            )}
          </div>
        </Rnd>

        <ChapterSettingsDialog
          outlineBid=''
          open={addChapterDialogOpen}
          onOpenChange={setAddChapterDialogOpen}
          variant='chapter'
          footerActionLabel={t('module.shifu.newChapter')}
          onFooterAction={handleAddChapterConfirm}
        />

        <div className='flex flex-1 h-full overflow-hidden text-sm flex-col'>
          <div className='flex flex-1 overflow-hidden'>
            <div
              className={cn(
                'flex-1 overflow-hidden',
                !isPreviewPanelOpen && 'relative',
              )}
            >
              <div
                className={cn(
                  'pt-5 px-6 flex flex-col h-full w-full mx-auto',
                  isPreviewPanelOpen ? 'pr-0' : 'max-w-[900px] relative',
                )}
              >
              {currentNode?.depth && currentNode.depth > 0 ? (
                <>
                  <div className='flex items-center gap-3 pb-2'>
                    <div className='flex flex-1 min-w-0 items-baseline gap-2'>
                      <h2 className='text-base font-semibold text-foreground whitespace-nowrap shrink-0'>
                        {t('module.shifu.creationArea.title')}
                      </h2>
                      <p className='flex-1 min-w-0 text-xs leading-3 text-[rgba(0,0,0,0.45)] truncate'>
                        {t('module.shifu.creationArea.description')}
                      </p>
                    </div>
                    <div className='ml-auto flex flex-nowrap items-center gap-2 relative shrink-0'>
                      <Tabs
                        value={editMode}
                        onValueChange={value => setEditMode(value as EditMode)}
                        className='shrink-0'
                      >
                        <TabsList className='h-8 rounded-full bg-muted/60 p-0 text-xs'>
                          {editModeOptions.map(option => (
                            <TabsTrigger
                              key={option.value}
                              value={option.value}
                              className={cn(
                                'mode-btn rounded-full px-3 py-1.5 data-[state=active]:bg-background data-[state=active]:text-foreground',
                              )}
                            >
                              {option.label}
                            </TabsTrigger>
                          ))}
                        </TabsList>
                      </Tabs>
                      <Button
                        type='button'
                        size='sm'
                        className='h-8 px-3 text-xs font-semibold text-[14px] shrink-0'
                        onClick={handlePreview}
                        disabled={!canPreview || isPreviewPreparing}
                        title={!canPreview ? previewDisabledReason : undefined}
                      >
                        {isPreviewPreparing ? (
                          <Loader2 className='h-4 w-4 animate-spin' />
                        ) : (
                          <Sparkles className='h-4 w-4' />
                        )}
                        {t('module.shifu.previewArea.action')}
                      </Button>
                    </div>
                  </div>
                  {!isPreviewPanelOpen && (
                    <Button
                      type='button'
                      variant='outline'
                      size='icon'
                      className='h-8 w-8 absolute top-[60px] right-[-13px] z-10'
                      onClick={handleTogglePreviewPanel}
                      aria-label={previewToggleLabel}
                      title={previewToggleLabel}
                    >
                      <Columns2 className='h-4 w-4' />
                    </Button>
                  )}
                  {isLoading ? (
                    <div className='h-40 flex items-center justify-center'>
                      <Loading />
                    </div>
                  ) : (
                    <MarkdownFlowEditor
                      locale={
                        normalizeLanguage(
                          (i18n.resolvedLanguage ?? i18n.language) as string,
                        ) as 'en-US' | 'zh-CN'
                      }
                      disabled={currentShifu?.readonly}
                      content={mdflow}
                      variables={variablesList}
                      systemVariables={systemVariablesList as any[]}
                      onChange={onChangeMdflow}
                      editMode={editMode}
                      uploadProps={uploadProps}
                    />
                  )}
                </>
              ) : null}
              </div>
            </div>

            {isPreviewPanelOpen ? (
              <div className='shrink-0 px-1 pt-[60px]'>
                <Button
                  type='button'
                  variant='outline'
                  size='icon'
                  className='h-8 w-8'
                  onClick={handleTogglePreviewPanel}
                  aria-label={previewToggleLabel}
                  title={previewToggleLabel}
                >
                  <Columns2 className='h-4 w-4' />
                </Button>
              </div>
            ) : null}
            {isPreviewPanelOpen ? (
              <div className='flex-1 overflow-hidden pt-5 px-6 pl-0'>
                <div className='h-full'>
                  <LessonPreview
                    loading={previewLoading}
                    errorMessage={previewError || undefined}
                    items={previewItems}
                    variables={previewVariables}
                    shifuBid={currentShifu?.bid || ''}
                    onRefresh={onRefresh}
                    onSend={onSend}
                    onVariableChange={onVariableChange}
                    variableOrder={variableOrder}
                    reGenerateConfirm={reGenerateConfirm}
                  />
                </div>
              </div>
            ) : null}
          </div>
          <div className="shifu-editor-footer">
            <a
              href="https://markdownflow.ai/"
              target="_blank"
              rel="noopener noreferrer"
              className="shifu-footer-link"
            >
              {t('module.chat.poweredBy')}
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScriptEditor;

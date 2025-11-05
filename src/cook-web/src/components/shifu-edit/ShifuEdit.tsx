'use client';
import React, { useState, useEffect, useMemo } from 'react';
import { Button } from '@/components/ui/Button';
import {
  ListCollapse,
  Loader2,
  PanelRightClose,
  PanelRightOpen,
  PlayIcon,
  Plus,
} from 'lucide-react';
import { useShifu } from '@/store';
import { useUserStore } from '@/store';
import OutlineTree from '@/components/outline-tree';
import '@mdxeditor/editor/style.css';
import Header from '../header';
import { UploadProps, MarkdownFlowEditor, EditMode } from 'markdown-flow-ui';
// import { UploadProps } from '../../../../../../markdown-flow-ui/src/components/MarkdownFlowEditor/uploadTypes';
// import MarkdownFlowEditor, { EditMode } from '../../../../../../markdown-flow-ui/src/components/MarkdownFlowEditor/MarkdownFlowEditor';
import 'markdown-flow-ui/dist/markdown-flow-ui.css';
import { cn } from '@/lib/utils';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import './shifuEdit.scss';
import Loading from '../loading';
import { useTranslation } from 'react-i18next';
import i18n, { normalizeLanguage } from '@/i18n';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { getBoolEnv } from '@/c-utils/envUtils';
import api from '@/api';
import LessonPreview from '@/components/lesson-preview';

const initializeEnvData = async (): Promise<void> => {
  const {
    updateAppId,
    updateCourseId,
    updateAlwaysShowLessonTree,
    updateUmamiWebsiteId,
    updateUmamiScriptSrc,
    updateEruda,
    updateBaseURL,
    updateLogoHorizontal,
    updateLogoVertical,
    updateEnableWxcode,
    updateSiteUrl,
  } = useEnvStore.getState() as EnvStoreState;

  const fetchEnvData = async (): Promise<void> => {
    try {
      const res = await fetch('/api/config', {
        method: 'GET',
        referrer: 'no-referrer',
      });
      if (res.ok) {
        const data = await res.json();

        // await updateCourseId(data?.courseId || '');
        await updateAppId(data?.wechatAppId || '');
        await updateAlwaysShowLessonTree(data?.alwaysShowLessonTree || 'false');
        await updateUmamiWebsiteId(data?.umamiWebsiteId || '');
        await updateUmamiScriptSrc(data?.umamiScriptSrc || '');
        await updateEruda(data?.enableEruda || 'false');
        await updateBaseURL(data?.apiBaseUrl || '');
        await updateLogoHorizontal(data?.logoHorizontal || '');
        await updateLogoVertical(data?.logoVertical || '');
        await updateEnableWxcode(data?.enableWechatCode?.toString() || 'true');
        await updateSiteUrl(data?.siteHost || '');
      }
    } catch (error) {
      console.error(error);
    } finally {
      const { umamiWebsiteId, umamiScriptSrc } =
        useEnvStore.getState() as EnvStoreState;
      if (getBoolEnv('eruda')) {
        import('eruda').then(eruda => eruda.default.init());
      }

      const loadUmamiScript = (): void => {
        if (umamiScriptSrc && umamiWebsiteId) {
          const script = document.createElement('script');
          script.defer = true;
          script.src = umamiScriptSrc;
          script.setAttribute('data-website-id', umamiWebsiteId);
          document.head.appendChild(script);
        }
      };

      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadUmamiScript);
      } else {
        loadUmamiScript();
      }
    }
  };
  await fetchEnvData();
};

const ScriptEditor = ({ id }: { id: string }) => {
  const { t } = useTranslation();
  const profile = useUserStore(state => state.userInfo);
  const [foldOutlineTree, setFoldOutlineTree] = useState(false);
  const [editMode, setEditMode] = useState<EditMode>('quickEdit' as EditMode);
  const [isPreviewPanelOpen, setIsPreviewPanelOpen] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
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

  const token = useUserStore(state => state.getToken());
  const baseURL = useEnvStore((state: EnvStoreState) => state.baseURL);

  useEffect(() => {
    void initializeEnvData();
  }, []);

  const onAddChapter = () => {
    actions.addChapter({
      parent_bid: '',
      bid: 'new_chapter',
      id: 'new_chapter',
      name: ``,
      children: [],
      position: '',
      depth: 0,
    });
    setTimeout(() => {
      document.getElementById('new_chapter')?.scrollIntoView({
        behavior: 'smooth',
      });
    }, 800);
  };

  useEffect(() => {
    actions.loadModels();
    if (id) {
      actions.loadChapters(id);
    }
  }, [id]);

  const handleTogglePreviewPanel = () => {
    setIsPreviewPanelOpen(prev => !prev);
  };

  const handlePreview = async () => {
    if (!canPreview || !currentShifu?.bid || !currentNode?.bid) {
      return;
    }

    setIsPreviewPanelOpen(true);
    setIsPreviewLoading(true);
    setPreviewError(null);

    try {
     
    } catch {
      setPreviewError(t('module.shifu.previewArea.error'));
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const variablesList = useMemo(() => {
    return variables.map((variable: string) => ({
      name: variable,
    }));
  }, [variables]);

  const systemVariablesList = useMemo(() => {
    return systemVariables.map((variable: Record<string, string>) => ({
      name: variable.name,
      label: variable.label,
    }));
  }, [systemVariables]);

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

  return (
    <div className='flex flex-col h-screen bg-gray-50'>
      <Header />
      <div className='flex-1 flex overflow-hidden scroll-y'>
        <div className='p-4 bg-white'>
          <div className='flex items-center justify-between gap-3'>
            <div
              onClick={() => setFoldOutlineTree(!foldOutlineTree)}
              className='rounded border bg-white p-1 cursor-pointer text-sm hover:bg-gray-200'
            >
              <ListCollapse className='h-5 w-5' />
            </div>
            {!foldOutlineTree && (
              <Button
                variant='outline'
                className='h-8 bottom-0 left-4 flex-1'
                size='sm'
                onClick={onAddChapter}
              >
                <Plus />
                {t('module.shifu.newChapter')}
              </Button>
            )}
          </div>

          {!foldOutlineTree && (
            <div className='flex-1 h-full overflow-y-auto overflow-x-hidden w-[256px] pb-10'>
              <ol className=' text-sm'>
                <OutlineTree
                  items={chapters}
                  onChange={newChapters => {
                    actions.setChapters([...newChapters]);
                  }}
                />
              </ol>
            </div>
          )}
        </div>
        <div className='flex-1 overflow-hidden relative text-sm'>
          <div className='flex h-full gap-4 overflow-hidden'>
            <div className={cn('flex-1 overflow-auto', isPreviewPanelOpen ? 'pr-2' : '')}>
              <div
                className={cn(
                  'p-8 gap-4 flex flex-col h-full w-full',
                  isPreviewPanelOpen ? 'max-w-[900px]' : 'max-w-[900px] mx-auto',
                )}
              >
                {isLoading ? (
                  <div className='h-40 flex items-center justify-center'>
                    <Loading />
                  </div>
                ) : currentNode?.depth && currentNode.depth > 0 ? (
                  <>
                    <div className='flex flex-wrap items-center gap-3'>
                      <div className='flex min-w-[220px] items-baseline gap-2'>
                        <h2 className='text-base font-semibold text-foreground'>
                          {t('module.shifu.creationArea.title')}
                        </h2>
                        <p className='px-2 text-xs leading-3 text-[rgba(0,0,0,0.45)]'>
                          {t('module.shifu.creationArea.description')}
                        </p>
                      </div>
                      <div className='ml-auto flex flex-wrap items-center gap-2'>
                        <Tabs
                          value={editMode}
                          onValueChange={value => setEditMode(value as EditMode)}
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
                          className='h-8 px-3 text-xs font-semibold'
                          onClick={handlePreview}
                          disabled={!canPreview || isPreviewLoading}
                          title={!canPreview ? previewDisabledReason : undefined}
                        >
                          {isPreviewLoading ? (
                            <Loader2 className='h-4 w-4 animate-spin' />
                          ) : (
                            <PlayIcon className='h-4 w-4' />
                          )}
                          {t('module.shifu.previewArea.action')}
                        </Button>
                        <Button
                          type='button'
                          variant='outline'
                          size='icon'
                          className='h-8 w-8'
                          onClick={handleTogglePreviewPanel}
                          aria-label={previewToggleLabel}
                          title={previewToggleLabel}
                        >
                          {isPreviewPanelOpen ? (
                            <PanelRightClose className='h-4 w-4' />
                          ) : (
                            <PanelRightOpen className='h-4 w-4' />
                          )}
                        </Button>
                      </div>
                    </div>
                    <MarkdownFlowEditor
                      locale={
                        normalizeLanguage(
                          (i18n.resolvedLanguage ?? i18n.language) as string,
                        ) as 'en-US' | 'zh-CN'
                      }
                      content={mdflow}
                      variables={variablesList}
                      systemVariables={systemVariablesList as any[]}
                      onChange={onChangeMdflow}
                      editMode={editMode}
                      uploadProps={uploadProps}
                    />
                  </>
                ) : null}
              </div>
            </div>
            {isPreviewPanelOpen ? (
              <div className='w-full max-w-[480px] flex-shrink-0 overflow-auto px-4 py-8'>
                <div className='h-full'>
                  <LessonPreview
                    loading={isPreviewLoading}
                    errorMessage={previewError}
                  />
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScriptEditor;

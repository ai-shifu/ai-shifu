'use client';
import React, { useState, useEffect, useMemo } from 'react';
import { Button } from '@/components/ui/Button';
import {
  Plus,
  ListCollapse,
} from 'lucide-react';
import { useShifu } from '@/store';
import { useUserStore } from '@/store';
import OutlineTree from '@/components/outline-tree';
import '@mdxeditor/editor/style.css';
import Header from '../header';
import { UploadProps, MarkdownFlowEditor, EditMode } from 'markdown-flow-ui'
// import MarkdownFlowEditor, { EditMode } from '../../../../../../markdown-flow-ui/src/components/MarkdownFlowEditor/MarkdownFlowEditor';
import 'markdown-flow-ui/dist/markdown-flow-ui.css';
import { cn } from '@/lib/utils';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import './shifuEdit.scss';
import Loading from '../loading';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import { getStringEnv } from '@/c-utils/envUtils';


const ScriptEditor = ({ id }: { id: string }) => {
  const { t } = useTranslation();
  const profile = useUserStore(state => state.userInfo);
  const [foldOutlineTree, setFoldOutlineTree] = useState(false);
  const [editMode, setEditMode] = useState<EditMode>('quickEdit' as EditMode);
  const editModeOptions = useMemo(
    () => [
      {
        label: t('shifu.creationArea.modeText'),
        value: 'quickEdit' as EditMode,
      },
      {
        label: t('shifu.creationArea.modeCode'),
        value: 'codeEdit' as EditMode,
      },
    ],
    [t],
  );

  useEffect(() => {
    if (profile) {
      i18n.changeLanguage(profile.language);
    }
  }, [profile]);
  
  const {
    mdflow,
    chapters,
    actions,
    isLoading,
    variables,
    systemVariables,
  } = useShifu();

  const token = useUserStore(state => state.getToken());

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
    actions.autoSaveBlocks();
  };

  const uploadProps: UploadProps = useMemo(() => ({
    action: `${getStringEnv('baseURL')}/api/shifu/upfile`,
    headers: {
      Authorization: `Bearer ${token}`,
      Token: token,
    },
  }), [token]);

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
                {t('shifu.newChapter')}
              </Button>
            )}
          </div>

          {!foldOutlineTree && (
            <div className='flex-1 h-full overflow-y-auto overflow-x-hidden w-[256px]'>
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
        <div className='flex-1 overflow-auto relative text-sm'>
          <div className='p-8 gap-4 flex flex-col max-w-[900px] mx-auto h-full w-full'>
            {isLoading ? (
              <div className='h-40 flex items-center justify-center'>
                <Loading />
              </div>
            ) : (
              <>
                <div className='flex items-center justify-between gap-4'>
                  <div className='flex items-center'>
                    <h2 className='text-base font-semibold text-foreground'>
                      {t('shifu.creationArea.title')}
                    </h2>
                    <p className='px-2 text-xs leading-3 text-[rgba(0,0,0,0.45)]'>
                      {t('shifu.creationArea.description')}
                    </p>
                  </div>
                  <Tabs
                    value={editMode}
                    onValueChange={value => setEditMode(value as EditMode)}
                    className='ml-auto'
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
                </div>
                <MarkdownFlowEditor 
                  locale={profile?.language as "en-US" | "zh-CN"} 
                  content={mdflow} 
                  variables={variablesList}
                  systemVariables={systemVariablesList as any[]}
                  onChange={onChangeMdflow}
                  editMode={editMode}
                  uploadProps={uploadProps}
                />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScriptEditor;

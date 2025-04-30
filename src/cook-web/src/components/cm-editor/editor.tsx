'use client';

import { useState, useCallback, useRef } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import {
  autocompletion,
  type CompletionContext,
  type CompletionResult,
} from '@codemirror/autocomplete';
import { EditorView } from '@codemirror/view';
import CustomDialog from './components/custom-dialog';
import EditorContext from './editor-context';
import type { Profile } from '@/components/profiles/type';
import ImageInject from './components/image-inject';
import VideoInject from './components/video-inject';
import ProfileInject from './components/profile-inject';
import { SelectedOption, IEditorContext } from './type';

function createSlashCommands(
  onSelectOption: (selectedOption: SelectedOption) => void,
) {
  return (context: CompletionContext): CompletionResult | null => {
    const word = context.matchBefore(/\/(\w*)$/);
    if (!word) return null;

    const handleSelect = (
      view: EditorView,
      _: any,
      from: number,
      to: number,
      selectedOption: SelectedOption,
    ) => {
      view.dispatch({
        changes: { from, to, insert: '' },
      });
      onSelectOption(selectedOption);
    };

    return {
      from: word.from,
      to: word.to,
      options: [
        {
          label: '变量',
          apply: (view, _, from, to) => {
            handleSelect(view, _, from, to, SelectedOption.Profile);
          },
        },
        {
          label: '图片',
          apply: (view, _, from, to) => {
            handleSelect(view, _, from, to, SelectedOption.Image);
          },
        },
        {
          label: '视频',
          apply: (view, _, from, to) => {
            handleSelect(view, _, from, to, SelectedOption.Video);
          },
        },
      ],
      filter: false,
    };
  };
}

type EditorProps = {
  content?: string;
  isEdit?: boolean;
  profiles?: string[];
  onChange?: (value: string, isEdit: boolean) => void;
};

const Editor: React.FC<EditorProps> = ({
  content = '',
  isEdit,
  profiles = [],
  onChange,
}) => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedOption, setSelectedOption] = useState<SelectedOption>(
    SelectedOption.Empty,
  );
  const [profileList, setProfileList] = useState<string[]>(profiles);

  const editorViewRef = useRef<EditorView | null>(null);

  const editorContextValue: IEditorContext = {
    selectedOption: SelectedOption.Empty,
    setSelectedOption,
    dialogOpen,
    setDialogOpen,
    profileList,
    setProfileList,
  };

  const onSelectedOption = useCallback((selectedOption: SelectedOption) => {
    setDialogOpen(true);
    setSelectedOption(selectedOption);
  }, []);

  const insertText = useCallback((text: string) => {
    if (!editorViewRef.current) return;

    const { state, dispatch } = editorViewRef.current;
    const changes = {
      from: state.selection.main.from,
      insert: text,
    };

    dispatch({
      changes,
      selection: { anchor: changes.from + text.length },
    });
  }, []);

  const handleSelectProfile = useCallback(
    (profile: Profile) => {
      const textToInsert = `{${profile.profile_key}}`;
      insertText(textToInsert);
      setDialogOpen(false);
    },
    [insertText, selectedOption],
  );

  const handleSelectResource = useCallback(
    (resourceUrl: string) => {
      const textToInsert = ` ${resourceUrl} `;
      insertText(textToInsert);
      setDialogOpen(false);
    },
    [insertText, selectedOption],
  );

  const slashCommandsExtension = useCallback(() => {
    return autocompletion({
      override: [createSlashCommands(onSelectedOption)],
    });
  }, [onSelectedOption]);

  const handleEditorUpdate = useCallback((view: EditorView) => {
    editorViewRef.current = view;
  }, []);

  return (
    <>
      <EditorContext.Provider value={editorContextValue}>
        {isEdit ? (
          <>
            <CodeMirror
              extensions={[
                EditorView.lineWrapping,
                slashCommandsExtension(),
                EditorView.updateListener.of((update) => {
                  handleEditorUpdate(update.view);
                }),
              ]}
              basicSetup={{
                lineNumbers: false,
                syntaxHighlighting: false,
                highlightActiveLine: false,
                highlightActiveLineGutter: false,
                foldGutter: false,
              }}
              className="border rounded-md"
              placeholder="输入“/”快速插入内容"
              value={content}
              theme="light"
              height="10em"
              onChange={(value: string) => {
                onChange?.(value, isEdit || false);
              }}
            />
            <CustomDialog>
              {selectedOption === SelectedOption.Profile && (
                <ProfileInject onSelect={handleSelectProfile} />
              )}
              {selectedOption === SelectedOption.Image && (
                <ImageInject onSelect={handleSelectResource} />
              )}
              {selectedOption === SelectedOption.Video && (
                <VideoInject onSelect={handleSelectResource} />
              )}
            </CustomDialog>
          </>
        ) : (
          <div className="w-full p-2 rounded cursor-pointer font-mono">
            {content}
          </div>
        )}
      </EditorContext.Provider>
    </>
  );
};
export default Editor;

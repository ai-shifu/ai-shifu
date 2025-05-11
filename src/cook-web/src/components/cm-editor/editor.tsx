'use client'

import { useState, useCallback, useRef } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import {
  autocompletion,
  type CompletionContext,
  type CompletionResult
} from '@codemirror/autocomplete'
import { EditorView } from '@codemirror/view'
import CustomDialog from './components/custom-dialog'
import EditorContext from './editor-context'
import type { Profile } from '@/components/profiles/type'
import ImageInject from './components/image-inject'
import VideoInject from './components/video-inject'
import ProfileInject from './components/profile-inject'
import { SelectedOption, IEditorContext } from './type'
import { useTranslation } from 'react-i18next'
/**
 * Creates a CodeMirror autocompletion source for slash commands, enabling insertion of variables, images, or videos.
 *
 * When the user types a slash followed by word characters (e.g., `/variable`), presents localized autocompletion options. Selecting an option clears the matched text and triggers the provided callback with the selected option type.
 *
 * @param onSelectOption - Callback invoked with the selected slash command option.
 * @returns A function compatible with CodeMirror's autocompletion API, providing slash command options.
 */
function createSlashCommands (
  onSelectOption: (selectedOption: SelectedOption) => void
) {
  return (context: CompletionContext): CompletionResult | null => {
    const word = context.matchBefore(/\/(\w*)$/)
    if (!word) return null

    const handleSelect = (
      view: EditorView,
      _: any,
      from: number,
      to: number,
      selectedOption: SelectedOption
    ) => {
      view.dispatch({
        changes: { from, to, insert: '' }
      })
      onSelectOption(selectedOption)
    }

    return {
      from: word.from,
      to: word.to,
      options: [
        {
          label: t('cm-editor.variable'),
          apply: (view, _, from, to) => {
            handleSelect(view, _, from, to, SelectedOption.Profile)
          }
        },
        {
          label: t('cm-editor.image'),
          apply: (view, _, from, to) => {
            handleSelect(view, _, from, to, SelectedOption.Image)
          }
        },
        {
          label: t('cm-editor.video'),
          apply: (view, _, from, to) => {
            handleSelect(view, _, from, to, SelectedOption.Video)
          }
        }
      ],
      filter: false
    }
  }
}

type EditorProps = {
  content?: string
  isEdit?: boolean
  profiles?: string[]
  onChange?: (value: string, isEdit: boolean) => void
}

const Editor: React.FC<EditorProps> = ({
  content = '',
  isEdit,
  profiles = [],
  onChange
}) => {
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false)
  const [selectedOption, setSelectedOption] = useState<SelectedOption>(
    SelectedOption.Empty
  )
  const [profileList, setProfileList] = useState<string[]>(profiles)

  const editorViewRef = useRef<EditorView | null>(null)

  const editorContextValue: IEditorContext = {
    selectedOption: SelectedOption.Empty,
    setSelectedOption,
    dialogOpen,
    setDialogOpen,
    profileList,
    setProfileList,
  }

  const onSelectedOption = useCallback((selectedOption: SelectedOption) => {
    setDialogOpen(true)
    setSelectedOption(selectedOption)
  }, [])

  const insertText = useCallback((text: string) => {
    if (!editorViewRef.current) return

    const { state, dispatch } = editorViewRef.current
    const changes = {
      from: state.selection.main.from,
      insert: text
    }

    dispatch({
      changes,
      selection: { anchor: changes.from + text.length }
    })
  }, [])

  const handleSelectProfile = useCallback(
    (profile: Profile) => {
      const textToInsert = `{${profile.profile_key}}`
      insertText(textToInsert)
      setDialogOpen(false)
    },
    [insertText, selectedOption]
  )

  const handleSelectResource = useCallback(
    (resourceUrl: string) => {
      const textToInsert = ` ${resourceUrl} `
      insertText(textToInsert)
      setDialogOpen(false)
    },
    [insertText, selectedOption]
  )

  const slashCommandsExtension = useCallback(() => {
    return autocompletion({
      override: [createSlashCommands(onSelectedOption)]
    })
  }, [onSelectedOption])

  const handleEditorUpdate = useCallback((view: EditorView) => {
    editorViewRef.current = view
  }, [])

  return (
    <>
      <EditorContext.Provider value={editorContextValue}>
        {isEdit ? (
          <>
            <CodeMirror
              extensions={[
                EditorView.lineWrapping,
                slashCommandsExtension(),
                EditorView.updateListener.of(update => {
                  handleEditorUpdate(update.view)
                })
              ]}
              basicSetup={{
                lineNumbers: false,
                syntaxHighlighting: false,
                highlightActiveLine: false,
                highlightActiveLineGutter: false,
                foldGutter: false
              }}
              className='border rounded-md'
              placeholder={t('cm-editor.input-slash-to-insert-content')}
              value={content}
              theme='light'
              height='10em'
              onChange={(value: string) => {
                onChange?.(value, isEdit || false)
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
          <div className='w-full p-2 rounded cursor-pointer font-mono'>
            {content}
          </div>
        )}
      </EditorContext.Provider>
    </>
  )
}
export default Editor

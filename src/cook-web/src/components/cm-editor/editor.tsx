'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { autocompletion } from '@codemirror/autocomplete'
import { EditorView } from '@codemirror/view'
import CustomDialog from './components/custom-dialog'
import EditorContext from './editor-context'
import type { Profile } from '@/components/profiles/type'
import ImageInject from './components/image-inject'
import VideoInject from './components/video-inject'
import ProfileInject from './components/profile-inject'
import { SelectedOption, IEditorContext } from './type'

import './index.css'

import {
  profilePlaceholders,
  imgPlaceholders,
  videoPlaceholders,
  createSlashCommands
} from './util'
import { useTranslation } from 'react-i18next'

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
  console.log('content', content)
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false)
  const [selectedOption, setSelectedOption] = useState<SelectedOption>(
    SelectedOption.Empty
  )
  const [profileList, setProfileList] = useState<string[]>(profiles)
  const [selectContentInfo, setSelectContentInfo] = useState<any>()
  const editorViewRef = useRef<EditorView | null>(null)

  const editorContextValue: IEditorContext = {
    selectedOption: SelectedOption.Empty,
    setSelectedOption,
    dialogOpen,
    setDialogOpen,
    profileList,
    setProfileList
  }

  const onSelectedOption = useCallback((selectedOption: SelectedOption) => {
    setDialogOpen(true)
    setSelectedOption(selectedOption)
  }, [])

  const insertText = useCallback(
    (text: string) => {
      if (!editorViewRef.current) return

      const { state, dispatch } = editorViewRef.current
      const from = state.selection.main.from

      dispatch({
        changes: { from, insert: text },
        selection: { anchor: from + text.length }
      })
    },
    [editorViewRef]
  )

  const deleteSelectedContent = useCallback(() => {
    if (
      !selectContentInfo ||
      !editorViewRef.current ||
      selectContentInfo.from === -1
    )
      return

    const { from, to } = selectContentInfo
    const { dispatch } = editorViewRef.current

    dispatch({
      changes: { from, to, insert: '' }
    })
  }, [selectContentInfo, editorViewRef])


  const handleSelectProfile = useCallback(
    (profile: Profile) => {
      const textToInsert = `{${profile.profile_key}}`
      if (selectContentInfo?.type === SelectedOption.Profile) {
        deleteSelectedContent()
        if (!editorViewRef.current) return

        const { dispatch } = editorViewRef.current
        dispatch({
          changes: { from: selectContentInfo.from, insert: textToInsert }
        })
      } else {
        insertText(textToInsert)
      }
      setDialogOpen(false)
    },
    [insertText, selectedOption]
  )

  const handleSelectImage = useCallback(
    (resourceUrl: string) => {
      const textToInsert = resourceUrl
      if (selectContentInfo?.type === SelectedOption.Image) {
        deleteSelectedContent()
        if (!editorViewRef.current) return
        const { dispatch } = editorViewRef.current
        dispatch({
          changes: { from: selectContentInfo.from, insert: textToInsert }
        })
      } else {
        insertText(textToInsert)
      }
      setDialogOpen(false)
    },
    [insertText, selectedOption]
  )

  const handleSelectVideo = useCallback(
    (resourceUrl: string) => {
      const textToInsert = resourceUrl
      if (selectContentInfo?.type === SelectedOption.Video) {
        deleteSelectedContent()
        if (!editorViewRef.current) return
        const { dispatch } = editorViewRef.current
        dispatch({
          changes: { from: selectContentInfo.from, insert: textToInsert }
        })
      } else {
        insertText(textToInsert)
      }
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

  const handleTagClick = useCallback(
    (event: any) => {
      const { type, content, from, to } = event.detail
      setSelectContentInfo({
        type,
        content,
        from,
        to
      })
      setSelectedOption(type)
      setDialogOpen(true)
    },
    [setSelectedOption, setDialogOpen]
  )

  useEffect(() => {
    if (!dialogOpen) {
      setSelectedOption(SelectedOption.Empty)
      setSelectContentInfo(null)
    }
  }, [dialogOpen])

  useEffect(() => {
    window.addEventListener('globalTagClick', handleTagClick)

    return () => {
      window.removeEventListener('globalTagClick', handleTagClick)
    }
  }, [handleTagClick])

  return (
    <>
      <EditorContext.Provider value={editorContextValue}>
        {isEdit ? (
          <>
            <CodeMirror
              extensions={[
                EditorView.lineWrapping,
                slashCommandsExtension(),
                profilePlaceholders,
                imgPlaceholders,
                videoPlaceholders,
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
                <ProfileInject
                  value={selectContentInfo?.content}
                  onSelect={handleSelectProfile}
                />
              )}
              {selectedOption === SelectedOption.Image && (
                <ImageInject
                  value={selectContentInfo?.content}
                  onSelect={handleSelectImage}
                />
              )}
              {selectedOption === SelectedOption.Video && (
                <VideoInject
                  value={selectContentInfo?.content}
                  onSelect={handleSelectVideo}
                />
              )}
            </CustomDialog>
          </>
        ) : (
          <div className='w-full p-2 rounded cursor-pointer font-mono break-words'>
            {content}
          </div>
        )}
      </EditorContext.Provider>
    </>
  )
}
export default Editor

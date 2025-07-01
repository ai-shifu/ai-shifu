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
  variablePlaceholders,
  imgPlaceholders,
  videoPlaceholders,
  createSlashCommands,
  parseContentInfo,
  getProfileKeyListFromContent
} from './util'
import { useTranslation } from 'react-i18next'

type EditorProps = {
  content?: string
  isEdit?: boolean
  onChange?: (value: string, variables: string[], isEdit: boolean) => void
  onBlur?: () => void
}

const Editor: React.FC<EditorProps> = ({
  content = '',
  isEdit,
  onChange,
  onBlur
}) => {
  const { t } = useTranslation()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [selectedOption, setSelectedOption] = useState<SelectedOption>(
    SelectedOption.Empty
  )
  const [selectContentInfo, setSelectContentInfo] = useState<any>()
  const editorViewRef = useRef<EditorView | null>(null)

  const editorContextValue: IEditorContext = {
    selectedOption: SelectedOption.Empty,
    setSelectedOption,
    dialogOpen,
    setDialogOpen,
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
      const textToInsert = `<span data-tag="profile">{${profile.profile_key}}</span>`
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
    ({
      resourceUrl,
      resourceTitle,
      resourceScale
    }: {
      resourceUrl?: string
      resourceTitle?: string
      resourceScale?: number
    }) => {
      // const textToInsert = resourceUrl
      const textToInsert = `<span data-tag="image" data-url="${resourceUrl}" data-title="${resourceTitle}" data-scale="${resourceScale}">${resourceTitle}</span>`
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
    ({
      resourceUrl,
      resourceTitle
    }: {
      resourceUrl: string
      resourceTitle: string
    }) => {
      // const textToInsert = resourceUrl
      const textToInsert = `<span data-tag="video" data-url="${resourceUrl}" data-title="${resourceTitle}">${resourceTitle}</span>`
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

  const handleTagClick = useCallback((event: any) => {
    event.stopPropagation()
    const { type, from, to, dataset } = event.detail
    const value = parseContentInfo(type, dataset)
    setSelectContentInfo({
      type,
      value,
      from,
      to
    })
    setSelectedOption(type)
    setDialogOpen(true)
  }, [])

  useEffect(() => {
    if (!dialogOpen) {
      setSelectedOption(SelectedOption.Empty)
      setSelectContentInfo(null)
    }
  }, [dialogOpen])

  useEffect(() => {
    const handleWrap = (e: any) => {
      if (e.detail.view === editorViewRef.current) {
        handleTagClick(e);
      }
    }
    window.addEventListener('globalTagClick', handleWrap)
    return () => {
      window.removeEventListener('globalTagClick', handleWrap)
    }
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
                variablePlaceholders,
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
              className='rounded-md'
              placeholder={t('cm-editor.input-slash-to-insert-content')}
              value={content}
              theme='light'
              minHeight='2rem'
              onChange={(value: string) => {
                onChange?.(value, getProfileKeyListFromContent(value), isEdit || false)
              }}
              onBlur={onBlur}
            />
            <CustomDialog>
              {selectedOption === SelectedOption.Profile && (
                <ProfileInject
                  value={selectContentInfo?.value}
                  onSelect={handleSelectProfile}
                />
              )}
              {selectedOption === SelectedOption.Image && (
                <ImageInject
                  value={selectContentInfo?.value}
                  onSelect={handleSelectImage}
                />
              )}
              {selectedOption === SelectedOption.Video && (
                <VideoInject
                  value={selectContentInfo?.value}
                  onSelect={handleSelectVideo}
                />
              )}
            </CustomDialog>
          </>
        ) : (
          <div className='w-full p-2 rounded cursor-pointer font-mono break-words whitespace-pre-wrap'>
            {content}
          </div>
        )}
      </EditorContext.Provider>
    </>
  )
}

export default Editor

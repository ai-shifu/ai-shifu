'use client'
import React, { useState, useEffect } from 'react'
import { DndProvider, useDrag, useDrop } from 'react-dnd'
import type { DropTargetMonitor } from 'react-dnd'
import { HTML5Backend } from 'react-dnd-html5-backend'
import { Button } from '@/components/ui/button'
import {
  Plus,
  GripVertical,
  Trash2,
  SquarePen,
  BugPlay,
  Settings2
} from 'lucide-react'
import { useShifu, useAuth } from '@/store'
import OutlineTree from '@/components/outline-tree'
import '@mdxeditor/editor/style.css'
import Header from '../header'
import { BlockType } from '@/types/shifu'
import RenderBlockContent, { useContentTypes } from '@/components/render-block'
import RenderBlockUI from '../render-ui'
import AIDebugDialog from '@/components/ai-debug'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from '../ui/alert-dialog'
import AddBlock from '@/components/add-block'
import Loading from '../loading'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n'
interface DragItem {
  id: string
  index: number
}

interface DraggableBlockProps {
  id: string
  type: BlockType
  index: number
  moveBlock: (dragIndex: number, hoverIndex: number) => void
  onClickDebug?: (id: string) => void
  onClickRemove?: (id: string) => void
  onClickChangeType?: (id: string, type: BlockType) => void
  children: React.ReactNode
  disabled?: boolean
  error?: string | null
}

const DraggableBlock = ({
  id,
  type,
  index,
  moveBlock,
  onClickDebug,
  onClickRemove,
  onClickChangeType,
  children,
  disabled = false,
  error
}: DraggableBlockProps) => {
  const { t } = useTranslation()
  const ref = React.useRef<HTMLDivElement>(null)

  const [{ handlerId }, drop] = useDrop<
    DragItem,
    void,
    { handlerId: string | symbol | null }
  >({
    accept: 'BLOCK',
    collect(monitor) {
      return {
        handlerId: monitor.getHandlerId()
      }
    },
    hover(item: DragItem, monitor: DropTargetMonitor) {
      if (!ref.current || disabled) {
        return
      }
      const dragIndex = item.index
      const hoverIndex = index

      if (dragIndex === hoverIndex) {
        return
      }

      const hoverBoundingRect = ref.current?.getBoundingClientRect()
      const hoverMiddleY =
        (hoverBoundingRect.bottom - hoverBoundingRect.top) / 2
      const clientOffset = monitor.getClientOffset()
      const hoverClientY = clientOffset!.y - hoverBoundingRect.top

      if (dragIndex < hoverIndex && hoverClientY < hoverMiddleY) {
        return
      }
      if (dragIndex > hoverIndex && hoverClientY > hoverMiddleY) {
        return
      }

      moveBlock(dragIndex, hoverIndex)
      item.index = hoverIndex
    }
  })

  const [{ isDragging }, drag] = useDrag<
    DragItem,
    void,
    { isDragging: boolean }
  >({
    type: 'BLOCK',
    item: () => {
      return { id, index }
    },
    canDrag: !disabled,
    collect: monitor => ({
      isDragging: monitor.isDragging()
    })
  })

  const [showMenu, setShowMenu] = useState(false)

  const handleMouseEnter = () => {
    setShowMenu(true)
  }

  const handleMouseLeave = () => {
    setShowMenu(false)
  }

  const dragRef = React.useRef<HTMLDivElement>(null)
  drop(ref)
  drag(dragRef)

  return (
    <div
      ref={ref}
      style={{ opacity: isDragging ? 0.5 : 1 }}
      data-handler-id={handlerId}
      className='group pl-7'
    >
      <div
        ref={dragRef}
        style={{
          border: error ? '1px solid #ff4d4f' : '1px solid #ddd',
          padding: '1rem',
          backgroundColor: '#fff',
          borderRadius: '8px',
          position: 'relative'
        }}
      >
        <div
          onMouseLeave={handleMouseLeave}
          className='group-hover:opacity-100 opacity-0 cursor-grab'
          style={{
            zIndex: 100,
            position: 'absolute',
            top: '0',
            left: '-56px'
          }}
        >
          <div className='p-2 h-8 w-16 flex items-center justify-center border color-[#999] rounded'>
            <SquarePen
              className='text-gray-500'
              onMouseEnter={handleMouseEnter}
            />
            <GripVertical
              className='text-gray-500'
              onMouseEnter={handleMouseEnter}
            />
          </div>

          <div
            className='shadow-md rounded-lg w-48 p-2 transition-all'
            style={{
              position: 'absolute',
              left: '0px',
              zIndex: 51,
              display: `${showMenu ? 'block' : 'none'}`,
              border: '1px solid #f3f4f6',
              backgroundColor: '#fff'
            }}
          >
            <div className='flex flex-col gap-2 text-sm'>
              <div className='px-3 py-1.5 text-gray-500 text-lg'>
                {type === 'ai' ? t('shifu.ai-block') : t('shifu.regular-block')}
              </div>
              <div
                className='flex items-center gap-2 px-3 py-1.5 rounded hover:bg-gray-50 cursor-pointer'
                onClick={() =>
                  onClickChangeType?.(id, type === 'ai' ? 'solidcontent' : 'ai')
                }
              >
                <Settings2 className='h-4 w-4' />
                {type === 'ai' ? t('shifu.setting-regular-block') : t('shifu.setting-ai-block')}
              </div>
              {type === 'ai' && <div
                className='flex items-center gap-2 px-3 py-1.5 rounded hover:bg-gray-50 cursor-pointer'
                onClick={() => onClickDebug?.(id)}
              >
                <BugPlay className='h-4 w-4' />
                {t('shifu.debug')}
              </div>}
              <div
                className='flex items-center gap-2 px-3 py-1.5 rounded hover:bg-red-50 text-red-600 cursor-pointer'
                onClick={() => onClickRemove?.(id)}
              >
                <Trash2 className='h-4 w-4' />
                {t('shifu.delete')}
              </div>
            </div>
          </div>
        </div>
        {error && (
          <div
            className="mb-2 p-2 bg-red-50 border border-red-200 rounded text-red-700 text-sm"
            role="alert"
            aria-live="polite"
          >
            {error}
          </div>
        )}
        {children}
      </div>
    </div>
  )
}

const ScriptEditor = ({ id }: { id: string }) => {
  const { t } = useTranslation()
  const { profile } = useAuth()
  const ContentTypes = useContentTypes()
  const [expandedBlocks, setExpandedBlocks] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (profile) {
      i18n.changeLanguage(profile.language)
    }
  }, [profile])
  const {
    blocks,
    chapters,
    actions,
    blockContentTypes,
    blockContentProperties,
    blockUIProperties,
    blockUITypes,
    currentNode,
    isLoading,
    currentShifu,
    blockErrors
  } = useShifu()

  const [debugBlockInfo, setDebugBlockInfo] = useState({
    blockId: '',
    visible: false
  })

  const [removeBlockInfo, setRemoveBlockInfo] = useState({
    blockId: '',
    visible: false
  })

  const onAddChapter = () => {
    actions.addChapter({
      parent_id: '',
      id: 'new_chapter',
      name: ``,
      children: [],
      no: '',
      depth: 0
    })
    setTimeout(() => {
      document.getElementById('new_chapter')?.scrollIntoView({
        behavior: 'smooth'
      })
    }, 800)
  }

  const onDebugBlock = (id: string) => {
    setDebugBlockInfo({ blockId: id, visible: true })
  }

  const onDebugBlockClose = () => {
    setDebugBlockInfo({ blockId: '', visible: false })
  }

  const onRemove = async (id: string) => {
    setRemoveBlockInfo({ blockId: id, visible: true })
  }

  const handleConfirmDelete = async (id: string | undefined) => {
    if (!id) return
    try {
      await actions.removeBlock(id, currentShifu?.shifu_id || '')
      setRemoveBlockInfo({ blockId: '', visible: false })
    } catch (error) {
      console.log(error)
    }
  }

  const onAddBlock = (index: number, type: BlockType, shifu_id: string) => {
    actions.addBlock(index, type, shifu_id)
  }

  const onChangeBlockType = (id: string, type: BlockType) => {
    const opt = ContentTypes.find(p => p.type === type)
    const mergeOpt = {
      ...opt,
      properties: {
        ...opt?.properties,
        prompt: blockContentProperties?.[id]?.prompt,
        profiles: blockContentProperties?.[id]?.profiles
      }
    }
    actions.setBlockContentTypesById(id, type)
    actions.setBlockContentPropertiesById(
      id,
      mergeOpt?.properties || ({} as any),
      true
    )
    actions.saveBlocks(currentShifu?.shifu_id || '')
  }

  useEffect(() => {
    actions.loadModels()
    if (id) {
      actions.loadChapters(id)
    }
  }, [id])

  return (
    <div className='flex flex-col h-screen bg-gray-50'>
      <Header />
      <div
        className='flex-1 container mx-auto px-10'
        style={{
          height: 'calc(100vh - 50px)',
          overflowY: 'auto'
        }}
      >
        <div
          style={{
            position: 'fixed',
            borderRadius: '8px',
            overflow: 'hidden',
            marginTop: '2rem',
            zIndex: 1
          }}
        >
          <div className='p-2 flex-1 h-full overflow-auto pr-4 w-[240px]'>
            <ol className=' text-sm'>
              <OutlineTree
                items={chapters}
                onChange={newChapters => {
                  actions.setChapters([...newChapters])
                }}
              />
            </ol>
            <Button
              variant='outline'
              className='my-2 h-8 sticky bottom-0 left-4 '
              size='sm'
              onClick={onAddChapter}
            >
              <Plus />
              {t('shifu.new_chapter')}
            </Button>
          </div>
        </div>

        <div
          className='flex-1 flex flex-col gap-4 p-8 pl-1 ml-0 overflow-auto relative text-sm bg-white'
          style={{
            paddingLeft: '240px'
          }}
        >
          {isLoading ? (
            <div className='h-40 flex items-center justify-center'>
              <Loading />
            </div>
          ) : (
            <>
              <DndProvider backend={HTML5Backend}>
                {blocks.map((block, index) => (
                  <DraggableBlock
                    key={block.properties.block_id}
                    id={block.properties.block_id}
                    type={
                      blockContentTypes[block.properties.block_id] as BlockType
                    }
                    index={index}
                    moveBlock={(dragIndex: number, hoverIndex: number) => {
                      const dragBlock = blocks[dragIndex]
                      const newBlocks = [...blocks]
                      newBlocks.splice(dragIndex, 1)
                      newBlocks.splice(hoverIndex, 0, dragBlock)
                      actions.setBlocks(newBlocks)
                      actions.autoSaveBlocks(
                        currentNode!.id,
                        newBlocks,
                        blockContentTypes,
                        blockContentProperties,
                        blockUITypes,
                        blockUIProperties,
                        currentShifu?.shifu_id || ''
                      )
                    }}
                    onClickChangeType={onChangeBlockType}
                    onClickDebug={onDebugBlock}
                    onClickRemove={onRemove}
                    disabled={expandedBlocks[block.properties.block_id]}
                    error={blockErrors[block.properties.block_id]}
                  >
                    <div
                      id={block.properties.block_id}
                      className='relative flex flex-col gap-2 '
                    >
                      <div className=' '>
                        <RenderBlockContent
                          id={block.properties.block_id}
                          type={blockContentTypes[block.properties.block_id]}
                          properties={
                            blockContentProperties[block.properties.block_id]
                          }
                        />
                      </div>
                      <RenderBlockUI
                        block={block}
                        onExpandChange={(expanded) => {
                          setExpandedBlocks(prev => ({
                            ...prev,
                            [block.properties.block_id]: expanded
                          }))
                        }}
                      />
                      <div>
                        <AddBlock
                          onAdd={(type: BlockType) => {
                            onAddBlock(index + 1, type, id)
                          }}
                        />
                      </div>
                    </div>
                  </DraggableBlock>
                ))}
              </DndProvider>
              {(currentNode?.depth || 0) > 0 && blocks.length === 0 && (
                <div className='flex flex-row items-center justify-start h-6 pl-8'>
                  <AddBlock onAdd={onAddBlock.bind(null, 0, 'ai', id)} />
                </div>
              )}
            </>
          )}
        </div>
      </div>
      {debugBlockInfo.visible && (
        <AIDebugDialog
          blockId={debugBlockInfo.blockId}
          open={true}
          onOpenChange={onDebugBlockClose}
        />
      )}

      <AlertDialog
        open={removeBlockInfo.visible}
        onOpenChange={(visible: boolean) => {
          setRemoveBlockInfo({
            ...removeBlockInfo,
            visible
          })
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('render-block.confirm-delete')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('render-block.confirm-delete-description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('render-block.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => handleConfirmDelete(removeBlockInfo.blockId)}
            >
              {t('render-block.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default ScriptEditor

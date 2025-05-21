'use client'
import React, { useState, useEffect } from 'react'
import { DndProvider, useDrag, useDrop } from 'react-dnd'
import type { DropTargetMonitor } from 'react-dnd'
import { HTML5Backend } from 'react-dnd-html5-backend'
import { Button } from '@/components/ui/button'
import { Plus, Variable, GripVertical, Trash2 } from 'lucide-react'
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
}

const DraggableBlock = ({
  id,
  type,
  index,
  moveBlock,
  onClickDebug,
  onClickRemove,
  onClickChangeType,
  children
}: DraggableBlockProps) => {
  const { t } = useTranslation()
  const ref = React.useRef<HTMLDivElement>(null)

  const [{ handlerId }, drop] = useDrop<
    DragItem,
    void,
    { handlerId: string | symbol | null }
  >({
    accept: 'BLOCK',
    collect (monitor) {
      return {
        handlerId: monitor.getHandlerId()
      }
    },
    hover (item: DragItem, monitor: DropTargetMonitor) {
      if (!ref.current) {
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
      className='relative group pl-7'
    >
      <div ref={dragRef}>
        <div
          onMouseLeave={handleMouseLeave}
          className='absolute top-0 left-0 w-10 h-10 cursor-move group-hover:opacity-100 opacity-0'
        >
          <GripVertical
            onMouseEnter={handleMouseEnter}
            className='h-4 w-4 shrink-0'
          />
          <div
            className='fixed bg-white hover:bg-gray-100 cursor-pointer rounded-sm w-100'
            style={{
              zIndex: 50,
              display: `${showMenu ? 'block' : 'none'}`
            }}
          >
            <div className='flex h-50'>{type === 'ai' ? 'AI' : '固定'}模块</div>
            <div
              className='flex h-50'
              onClick={() => onClickChangeType?.(id, type === 'ai' ? 'solidcontent' : 'ai')}
            >
              <Variable />
              设置成{type === 'ai' ? '固定' : 'AI'}模块
            </div>
            <div className='flex h-50' onClick={() => onClickDebug?.(id)}>
              <Variable />
              {t('scenario.debug')}
            </div>
            <div className='flex h-50' onClick={() => onClickRemove?.(id)}>
              <Trash2 className='h-5 w-5 cursor-pointer' />
              删除
            </div>
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}

const ScriptEditor = ({ id }: { id: string }) => {
  const { t } = useTranslation()
  const { profile } = useAuth()
  const ContentTypes = useContentTypes()
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
    currentShifu
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
    await actions.removeBlock(id, currentShifu?.shifu_id || '')
    setRemoveBlockInfo({ blockId: '', visible: false })
  }

  const onAddBlock = (index: number, type: BlockType, shifu_id: string) => {
    actions.addBlock(index, type, shifu_id)
  }

  const onChangeBlockType = (id: string, type: BlockType) => {
    const opt = ContentTypes.find(p => p.type === type)
    actions.setBlockContentTypesById(id, type)
    actions.setBlockContentPropertiesById(
      id,
      opt?.properties || ({} as any),
      true
    )
    console.log('onChangeBlockType opt', id, type, opt)
    actions.saveBlocks(currentShifu?.shifu_id || '')
  }

  useEffect(() => {
    actions.loadModels()
    if (id) {
      actions.loadChapters(id)
    }
  }, [id])

  return (
    <div className='flex flex-col h-screen bg-gray-50 overflow-hidden '>
      <Header />
      <div className='flex-1 container mx-auto flex flex-row  overflow-hidden px-10'>
        <div className='p-2 flex flex-col overflow-hidden h-full'>
          <div className='flex-1 h-full overflow-auto pr-4 w-[240px]'>
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
              {t('scenario.new_chapter')}
            </Button>
          </div>
        </div>

        <div className='flex-1 flex flex-col gap-4 p-8 pl-1 ml-0 overflow-auto relative bg-white text-sm'>
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
                    type={blockContentTypes[block.properties.block_id] as BlockType}
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
                      <RenderBlockUI block={block} />
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

'use client'
import {
  SortableTree,
  SimpleTreeItemWrapper,
  TreeItemComponentProps,
  TreeItems
} from '../dnd-kit-sortable-tree'
import React, { useState } from 'react'
import { Outline } from '@/types/shifu'
import { cn } from '@/lib/utils'
import {
  Plus,
  Trash2,
  Edit,
  SlidersHorizontal,
  MoreVertical
} from 'lucide-react'
import { InlineInput } from '../inline-input'
import { useShifu } from '@/store/useShifu'
import Loading from '../loading'
import { ItemChangedReason } from '../dnd-kit-sortable-tree/types'
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator
} from '../ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { useTranslation } from 'react-i18next'
import { useAlert } from '@/components/ui/use-alert'
import ChapterSettingsDialog from '../chapter-setting'

interface ICataTreeProps {
  currentNode?: Outline
  items: TreeItems<Outline>
  onChange?: (data: TreeItems<Outline>) => void
  onAddNodeClick?: (node: Outline) => void
}


const getReorderOutlineDto = (items: TreeItems<Outline>) => {
  return items.map(item => {
    return {
      bid: item.bid,
      children: getReorderOutlineDto(item?.children || [])
    }
  })
}

export const CataTree = React.memo((props: ICataTreeProps) => {
  const { items, onChange } = props
  const { actions, focusId } = useShifu()
  const onItemsChanged = async (
    data: TreeItems<Outline>,
    reason: ItemChangedReason<Outline>
  ) => {
    if (reason.type == 'dropped') {

      const reorderOutlineDtos = getReorderOutlineDto(data)
      await actions.reorderOutlineTree(reorderOutlineDtos)

    }

    onChange?.(data)
  }

  return (
    <SortableTree
      disableSorting={!!focusId}
      items={items}
      indentationWidth={20}
      onItemsChanged={onItemsChanged}
      TreeItemComponent={props => {
        return <MinimalTreeItemComponent {...props} />
      }}
      dropAnimation={null}
    />
  )
})

CataTree.displayName = 'CataTree'

export type TreeItemProps = {
  currentNode?: Outline
  onChange?: (node: Outline, value: string) => void
}

const MinimalTreeItemComponent = React.forwardRef<
  HTMLDivElement,
  TreeItemComponentProps<Outline> & TreeItemProps
>((props, ref) => {
  const { focusId, actions, cataData, currentNode, currentShifu } = useShifu()
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [settingsDialogOpen, setSettingsDialogOpen] = useState(false)
  const { t } = useTranslation()
  const alert = useAlert()
  const onNodeChange = async (value: string) => {
    if (!value || value.trim() === '') {
      alert.showAlert({
        title: t('outline-tree.name-required'),
        description: '',
        confirmText: t('common.confirm'),
        onConfirm () {
          actions.removeOutline({ parent_bid: props.item.parentId, ...props.item })
          actions.setFocusId('')
        }
      })
      return
    }
    await actions.createOutline({
      shifu_bid: currentShifu?.bid || '',
      id: props.item.id,
      parent_bid: props.item.parent_bid || '',
      bid: props.item.bid,
      name: value,
      children: [],
      position: ''
    })
  }
  const onAddNodeClick = (node: Outline) => {
    if (node.depth && node.depth >= 1) {
      actions.addSiblingOutline(node, '')
    } else {
      actions.addSubOutline(node, '')
    }
  }
  const removeNode = async e => {
    e.stopPropagation()
    setShowDeleteDialog(true)
  }
  const editNode = e => {
    e.stopPropagation()
    actions.setFocusId(props.item.id || '')
  }
  const onSelect = async () => {
    if (props.item.id == 'new_chapter') {
      return
    }

    if (props.item.depth == 0) {
      await actions.setCurrentNode(props.item)
      actions.setBlocks([])
      return
    }

    await actions.setCurrentNode(props.item)
    await actions.loadBlocks(props.item.bid || '', currentShifu?.bid || '')
  }

  const handleConfirmDelete = async () => {
    await actions.removeOutline({ parent_bid: props.item.parentId, ...props.item })
    setShowDeleteDialog(false)
  }

  return (
    <>
      <SimpleTreeItemWrapper
        {...props}
        ref={ref}
        disableCollapseOnItemClick={false}
      >
        <div
          id={props.item.id}
          className={cn(
            'flex items-center flex-1 justify-between w-full group p-2 rounded-md',
            (props.item?.children?.length || 0) > 0 ? 'pl-0' : 'pl-4',
            (currentNode?.id == props.item.id &&
              (props.item?.depth || 0) > 0) ||
              props.item.id === 'new_chapter'
              ? 'bg-gray-200'
              : ''
          )}
          onClick={onSelect}
        >
          <span className='flex flex-row items-center whitespace-nowrap overflow-hidden text-ellipsis'>
            <InlineInput
              isEdit={focusId === props.item.id}
              value={cataData[props.item.id!]?.name || ''}
              onChange={onNodeChange}
              onFocus={() => {
                actions.setFocusId(props.item.id || '')
              }}
            />
          </span>
          {(props.item?.depth || 0 > 0) && (
            <div className='flex items-center space-x-1'>
              {cataData[props.item.id!]?.status == 'saving' && (
                <Loading className='h-4 w-4' />
              )}
            </div>
          )}
          {(props.item?.depth || 0 > 0) && (
            <div
              className={cn(
                'items-center space-x-2 flex',
                !dropdownOpen
                  ? 'group-hover:opacity-100 opacity-0 transition-opacity'
                  : 'opacity-100'
              )}
            >
              {props.item.id !== 'new_chapter' ? (
                <DropdownMenu onOpenChange={setDropdownOpen}>
                  <DropdownMenuTrigger asChild>
                    <Button variant='ghost' size='icon' className='h-8 w-8'>
                      <MoreVertical className='h-4 w-4' />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align='start'
                    side='bottom'
                    alignOffset={-5}
                    className='w-[160px]'
                  >
                    <DropdownMenuItem onClick={editNode}>
                      <Edit className='mr-2 h-4 w-4' />
                      <span>{t('outline-tree.edit')}</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={e => {
                        e.stopPropagation()
                        setSettingsDialogOpen(true)
                      }}
                    >
                      <SlidersHorizontal className='mr-2 h-4 w-4' />
                      <span>{t('outline-tree.setting')}</span>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={removeNode}
                      className='text-destructive'
                    >
                      <Trash2 className='mr-2 h-4 w-4' />
                      <span>{t('outline-tree.delete')}</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <>
                  <Trash2 className='mr-2 h-4 w-4' onClick={removeNode} />
                </>
              )}
            </div>
          )}
          {(props.item?.depth || 0) <= 0 && (
            <div
              className={cn(
                'items-center space-x-2 flex',
                !dropdownOpen
                  ? 'group-hover:opacity-100 opacity-0 transition-opacity'
                  : 'opacity-100'
              )}
            >
              {props.item.id !== 'new_chapter' ? (
                <>
                  <DropdownMenu onOpenChange={setDropdownOpen}>
                    <DropdownMenuTrigger asChild>
                      <Button variant='ghost' size='icon' className='h-8 w-8'>
                        <MoreVertical className='h-4 w-4' />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align='start'
                      side='bottom'
                      alignOffset={-5}
                      className='w-[160px]'
                    >
                      <DropdownMenuItem onClick={editNode}>
                        <Edit className='mr-2 h-4 w-4' />
                        <span>{t('outline-tree.edit')}</span>
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={removeNode}
                        className='text-destructive'
                      >
                        <Trash2 className='mr-2 h-4 w-4' />
                        <span>{t('outline-tree.delete')}</span>
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                  {cataData[props.item.id!]?.status == 'saving' && (
                    <Loading className='h-4 w-4' />
                  )}
                  {cataData[props.item.id!]?.status !== 'saving' && (
                    <Button
                      variant='ghost'
                      size='icon'
                      className='h-8 w-8'
                      onClick={e => {
                        e.stopPropagation()
                        onAddNodeClick?.(props.item)
                      }}
                    >
                      <Plus className='h-4 w-4' />
                    </Button>
                  )}
                </>
              ) : (
                <>
                  <Trash2 className='mr-2 h-4 w-4' onClick={removeNode} />
                </>
              )}
            </div>
          )}
        </div>
      </SimpleTreeItemWrapper>
      <ChapterSettingsDialog
        outlineBid={props.item.bid}
        open={settingsDialogOpen}
        onOpenChange={setSettingsDialogOpen}
      />
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('outline-tree.confirm-delete')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('outline-tree.confirm-delete-description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('outline-tree.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmDelete}>
              {t('outline-tree.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
})

MinimalTreeItemComponent.displayName = 'MinimalTreeItemComponent'

export default CataTree

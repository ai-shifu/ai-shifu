"use client"
import { SortableTree, SimpleTreeItemWrapper, TreeItemComponentProps, TreeItems } from '../dnd-kit-sortable-tree';
import React, { useState } from 'react';
import { Outline } from '@/types/shifu';
import { cn } from '@/lib/utils';
import { Plus, Trash2, Edit } from 'lucide-react';
import { InlineInput } from '../inline-input';
import { useShifu } from '@/store/useShifu';
import Loading from '../loading';
import ChapterSetting from '../chapter-setting';
import { ItemChangedReason } from '../dnd-kit-sortable-tree/types';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../ui/alert-dialog';
import { useTranslation } from 'react-i18next';
interface ICataTreeProps {
    currentNode?: Outline;
    items: TreeItems<Outline>;
    onChange?: (data: TreeItems<Outline>) => void;
    onAddNodeClick?: (node: Outline) => void;
}

export const CataTree = React.memo((props: ICataTreeProps) => {
    const { items, onChange, } = props;
    const { actions } = useShifu();
    const onItemsChanged = async (data: TreeItems<Outline>, reason: ItemChangedReason<Outline>) => {
        if (reason.type == 'dropped') {
            const parentId = reason.draggedItem.parentId;
            if (parentId) {
                const parent = data.find((item) => item.id == parentId);
                const ids = parent?.children?.map((item) => item.id) || [];
                await actions.updateChapterOrder(ids);
            } else {
                const ids = data.map((item) => item.id);
                await actions.updateChapterOrder(ids);
            }

        }

        onChange?.(data);
    }

    return (
        <SortableTree
            disableSorting={false}
            items={items}
            indentationWidth={20}
            onItemsChanged={onItemsChanged}
            TreeItemComponent={(props) => {
                return (
                    <MinimalTreeItemComponent
                        {...props}
                    />
                )
            }}
            dropAnimation={null}
        />
    );
});

CataTree.displayName = 'CataTree';

export type TreeItemProps = {
    currentNode?: Outline;
    onChange?: (node: Outline, value: string) => void;
}

const MinimalTreeItemComponent = React.forwardRef<
    HTMLDivElement,
    TreeItemComponentProps<Outline> & TreeItemProps
>((props, ref) => {
    const { focusId, actions, cataData, currentNode, currentShifu } = useShifu();
    const [showDeleteDialog, setShowDeleteDialog] = useState(false);
    const { t } = useTranslation();
    const onNodeChange = async (value: string) => {
        if (props.item.depth == 0) {
            await actions.createChapter({
                parent_id: props.item.parentId,
                id: props.item.id,
                name: value,
                children: [],
                no: '',
            })
        } else if (props.item.depth == 1) {
            await actions.createUnit({
                parent_id: props.item.parentId,// cataData[props.item.id!]?.parent_id,
                id: props.item.id,
                name: value,
                children: [],
                no: '',
            })
        }
    }
    const onAddNodeClick = (node: Outline) => {
        if (node.depth && node.depth >= 1) {
            actions.addSiblingOutline(node, "");
        } else {
            actions.addSubOutline(node, "");
        }
    }
    const removeNode = async (e) => {
        e.stopPropagation();
        setShowDeleteDialog(true);
    }
    const editNode = (e) => {
        e.stopPropagation();
        actions.setFocusId(props.item.id || "");
    }
    const onSelect = async () => {
        if (props.item.id == 'new_chapter') {
            return;
        }

        if (props.item.depth == 0) {
            await actions.setCurrentNode(props.item);
            actions.setBlocks([]);
            return;
        }

        await actions.setCurrentNode(props.item);
        await actions.loadBlocks(props.item.id || "", currentShifu?.shifu_id || "");
    }

    const handleConfirmDelete = async () => {
        await actions.removeOutline(props.item);
        setShowDeleteDialog(false);
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
                        'flex items-center flex-1 px-0 py-1 justify-between w-full group',
                        (props.item?.children?.length || 0) > 0 ? 'pl-0' : 'pl-4',
                        currentNode?.id == props.item.id ? 'bg-gray-100' : ''
                    )}
                    onClick={onSelect}
                >
                    <span className='flex flex-row items-center w-40 whitespace-nowrap overflow-hidden text-ellipsis' >
                        <InlineInput
                            isEdit={focusId === props.item.id}
                            value={cataData[props.item.id!]?.name || ""}
                            onChange={onNodeChange}
                            onFocus={() => {
                                actions.setFocusId(props.item.id || "")
                            }}
                        />
                    </span>
                    {
                        (props.item?.depth || 0 > 0) && (
                            <div className='flex items-center space-x-1'>
                                {
                                    cataData[props.item.id!]?.status == 'saving' && (
                                        <Loading className='h-4 w-4' />
                                    )
                                }
                            </div>
                        )
                    }
                    {
                        (props.item?.depth || 0 > 0) && (
                            <div className='items-center space-x-2 hidden group-hover:flex'>
                                <Edit
                                    className='cursor-pointer h-4 w-4 text-gray-500'
                                    onClick={editNode}
                                />
                                <div onClick={(e) => {
                                    e.stopPropagation();
                                }}>
                                    <ChapterSetting unitId={props.item.id} />
                                </div>
                                <Trash2 className='cursor-pointer h-4 w-4 text-gray-500' onClick={removeNode} />
                            </div>
                        )
                    }
                    {
                        ((props.item?.depth || 0) <= 0) && (
                            <div className='items-center space-x-2 hidden group-hover:flex'>
                                <Edit
                                    className='cursor-pointer h-4 w-4 text-gray-500'
                                    onClick={editNode}
                                />
                                {
                                    cataData[props.item.id!]?.status == 'saving' && (
                                        <Loading className='h-4 w-4' />
                                    )
                                }
                                {
                                    cataData[props.item.id!]?.status !== 'saving' && (
                                        <Plus className='cursor-pointer h-4 w-4 text-gray-500' onClick={(e) => {
                                            e.stopPropagation();
                                            onAddNodeClick?.(props.item);
                                        }} />
                                    )
                                }
                                <Trash2 className='cursor-pointer h-4 w-4 text-gray-500' onClick={removeNode} />
                            </div>
                        )
                    }
                </div>
            </SimpleTreeItemWrapper>

            <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t('outline-tree.confirm-delete')}</AlertDialogTitle>
                        <AlertDialogDescription>
                            {t('outline-tree.confirm-delete-description')}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>{t('outline-tree.cancel')}</AlertDialogCancel>
                        <AlertDialogAction onClick={handleConfirmDelete}>{t('outline-tree.confirm')}</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    )
});

MinimalTreeItemComponent.displayName = 'MinimalTreeItemComponent';

export default CataTree;

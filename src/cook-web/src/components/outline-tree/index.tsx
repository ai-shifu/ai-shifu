"use client"
import { SortableTree, SimpleTreeItemWrapper, TreeItemComponentProps, TreeItems } from '../dnd-kit-sortable-tree';
import React from 'react';
import { Outline } from '@/types/scenario';
import { cn } from '@/lib/utils';
import { Plus, Trash } from 'lucide-react';
import { InlineInput } from '../inline-input';
import { useScenario } from '@/store/useScenario';
import Loading from '../loading';
interface ICataTreeProps {
    currentNode?: Outline;
    items: TreeItems<Outline>;
    onChange?: (data: TreeItems<Outline>) => void;
    onAddNodeClick?: (node: Outline) => void;
}

export const CataTree = React.memo((props: ICataTreeProps) => {
    const { items, onChange, } = props;
    const onItemsChanged = (data: TreeItems<Outline>) => {

        onChange?.(data);
    }

    const onAddNodeClick = (node: Outline) => {
        props.onAddNodeClick?.(node);
    }

    return (
        <SortableTree
            disableSorting={true}
            items={items}
            indentationWidth={20}
            onItemsChanged={onItemsChanged}
            TreeItemComponent={(props) => {
                return (
                    <MinimalTreeItemComponent
                        {...props}
                        onAddNodeClick={onAddNodeClick}
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
    const { focusId, actions, cataData } = useScenario();

    const onNodeChange = async (value: string) => {

        if (props.item.depth == 0) {
            await actions.createChapter({
                parent_id: cataData[props.item.id!]?.parent_id,
                id: props.item.id,
                name: value,
                children: [],
                no: '',
            })
        } else if (props.item.depth == 1) {
            await actions.createUnit({
                parent_id: cataData[props.item.id!]?.parent_id,
                id: props.item.id,
                name: value,
                children: [],
                no: '',
            })
        } else {
            await actions.createSiblingUnit({
                parent_id: cataData[props.item.id!]?.parent_id,
                id: props.item.id,
                name: value,
                children: [],
                no: '',
            })
        }


        actions.setFocusId("");
    }
    const onAddNodeClick = (node: Outline) => {
        console.log(node)
        if (node.depth && node.depth >= 1) {
            actions.addSiblingOutline(node, "");
        } else {
            actions.addSubOutline(node, "");
        }
    }
    const removeNode = async () => {
        await actions.removeOutline(props.item);
    }
    const onSelect = () => {
        actions.loadBlocks(props.item.id || "");
    }
    return (
        <SimpleTreeItemWrapper {...props} ref={ref}>
            <div
                className={cn(
                    'flex items-center flex-1 px-0 py-1 justify-between w-full',
                    (props.item?.children?.length || 0) > 0 ? 'pl-0' : 'pl-4'
                )}
                onClick={onSelect}
            >
                <span className='w-40 whitespace-nowrap overflow-hidden text-ellipsis' >
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
                            {
                                cataData[props.item.id!]?.status !== 'saving' && (
                                    <Plus className='cursor-pointer h-5 w-5 text-gray-500' onClick={(e) => {
                                        e.stopPropagation();
                                        onAddNodeClick?.(props.item);
                                    }} />
                                )
                            }
                            <Trash className='cursor-pointer h-4 w-4 text-gray-500' onClick={removeNode} />
                        </div>
                    )
                }
                {
                    ((props.item?.depth || 0) <= 0) && (
                        <div className='flex items-center space-x-1'>
                            {
                                cataData[props.item.id!]?.status == 'saving' && (
                                    <Loading className='h-4 w-4' />
                                )
                            }
                            {
                                cataData[props.item.id!]?.status !== 'saving' && (
                                    <Plus className='cursor-pointer h-5 w-5 text-gray-500' onClick={(e) => {
                                        e.stopPropagation();
                                        onAddNodeClick?.(props.item);
                                    }} />
                                )
                            }
                            <Trash className='cursor-pointer h-4 w-4 text-gray-500' onClick={removeNode} />

                        </div>
                    )
                }

            </div>
        </SimpleTreeItemWrapper >
    )
});

MinimalTreeItemComponent.displayName = 'MinimalTreeItemComponent';


export default CataTree;

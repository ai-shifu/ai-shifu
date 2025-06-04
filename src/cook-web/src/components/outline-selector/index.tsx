"use client"
import { SortableTree, SimpleTreeItemWrapper, TreeItemComponentProps, TreeItems } from '../dnd-kit-sortable-tree';
import React, { useState } from 'react';
import { Outline } from '@/types/shifu';
import { cn } from '@/lib/utils';
import { useShifu } from '@/store/useShifu';
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '../ui/dropdown-menu';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
interface ICataTreeProps {
    currentNode?: Outline;
    items: TreeItems<Outline>;
    onChange?: (data: TreeItems<Outline>) => void;
    onSelect?: (node: Outline) => void;
}

export const CataTree = React.memo((props: ICataTreeProps) => {
    const { items, onChange, } = props;

    const onItemsChanged = (data: TreeItems<Outline>) => {
        onChange?.(data);
    }
    const onSelect = (node: Outline) => {
        props.onSelect?.(node);
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
                        onSelect={onSelect}
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
    onSelect?: (node: Outline) => void;
}
const MinimalTreeItemComponent = React.forwardRef<
    HTMLDivElement,
    TreeItemComponentProps<Outline> & TreeItemProps
>((props, ref) => {
    const { cataData } = useShifu();

    const onSelect = () => {
        props.onSelect?.(props.item!);
    }
    return (
        <SimpleTreeItemWrapper {...props} ref={ref}>
            <div
                className={cn(
                    'flex text-sm items-center flex-1 px-0 py-1 justify-between w-full',
                    (props.item?.children?.length || 0) > 0 ? 'pl-0' : 'pl-4'
                )}
                onClick={onSelect}
            >
                <span className='w-40 whitespace-nowrap overflow-hidden text-ellipsis' >
                    {cataData[props.item.id!]?.name || ""}
                </span>

            </div>
        </SimpleTreeItemWrapper >
    )
});

MinimalTreeItemComponent.displayName = 'MinimalTreeItemComponent';


export default function OutlineSelector({ value, chapters = [], onSelect }: { value: string, chapters: Outline[], onSelect?: (node: Outline) => void }) {
    "use client"
    const { t } = useTranslation();
    const [nodes, setNodes] = useState(chapters);
    const [open, setOpen] = useState(false);
    const [selectedNode, setSelectedNode] = useState<Outline | null>(null);
    const onNodeSelect = (node: Outline) => {
        setOpen(false);
        onSelect?.(node);
        setSelectedNode(node);
        value = node.id;
    }
    useEffect(() => {
        for (const chapter of chapters) {
            if (chapter.id === value) {
                setSelectedNode(chapter);
                return;
            }
            for (const child of chapter.children || []) {
                if (child.id === value) {
                    setSelectedNode(child);
                    return;
                }
            }

        }
    }, [value,chapters]);
    return (
        <DropdownMenu open={open} onOpenChange={setOpen}>
            <DropdownMenuTrigger>
                {
                    selectedNode ? (selectedNode.no + ":" + selectedNode.name) : t('outline-selector.select-chapter')
                }
            </DropdownMenuTrigger>
            <DropdownMenuContent align='start'>
                <CataTree
                    items={nodes}
                    onSelect={onNodeSelect}
                    onChange={(newChapters) => {
                        setNodes([...newChapters]);
                    }}
                />
            </DropdownMenuContent>
        </DropdownMenu>

    )
}

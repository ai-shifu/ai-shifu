"use client"
import React, { useState, useEffect, MouseEventHandler } from 'react';
import { DndProvider, useDrag, useDrop } from 'react-dnd';
import type { DropTargetMonitor } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { Button } from '@/components/ui/button';
import { ChevronsRight, Plus, Variable, GripVertical } from 'lucide-react';
import { useShifu, useAuth } from '@/store';
import OutlineTree from '@/components/outline-tree'
import '@mdxeditor/editor/style.css'
import Header from '../header';
import { BlockType } from '@/types/shifu';
import RenderBlockContent from '../render-block';
import RenderBlockUI from '../render-ui';
import AIDebugDialog from '@/components/ai-debug';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../ui/dropdown-menu';
import AddBlock from '@/components/add-block';
import Loading from '../loading';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
interface DragItem {
    id: string;
    index: number;
}

interface DraggableBlockProps {
    id: string;
    index: number;
    moveBlock: (dragIndex: number, hoverIndex: number) => void;
    children: React.ReactNode;
}

const DraggableBlock = ({ id, index, moveBlock, children }: DraggableBlockProps) => {

    const ref = React.useRef<HTMLDivElement>(null);

    const [{ handlerId }, drop] = useDrop<DragItem, void, { handlerId: string | symbol | null }>({
        accept: 'BLOCK',
        collect(monitor) {
            return {
                handlerId: monitor.getHandlerId(),
            };
        },
        hover(item: DragItem, monitor: DropTargetMonitor) {
            if (!ref.current) {
                return;
            }
            const dragIndex = item.index;
            const hoverIndex = index;

            if (dragIndex === hoverIndex) {
                return;
            }

            const hoverBoundingRect = ref.current?.getBoundingClientRect();
            const hoverMiddleY = (hoverBoundingRect.bottom - hoverBoundingRect.top) / 2;
            const clientOffset = monitor.getClientOffset();
            const hoverClientY = clientOffset!.y - hoverBoundingRect.top;

            if (dragIndex < hoverIndex && hoverClientY < hoverMiddleY) {
                return;
            }
            if (dragIndex > hoverIndex && hoverClientY > hoverMiddleY) {
                return;
            }

            moveBlock(dragIndex, hoverIndex);
            item.index = hoverIndex;
        },
    });

    const [{ isDragging }, drag] = useDrag<DragItem, void, { isDragging: boolean }>({
        type: 'BLOCK',
        item: () => {
            return { id, index };
        },
        collect: (monitor) => ({
            isDragging: monitor.isDragging(),
        }),
    });

    const dragRef = React.useRef<HTMLDivElement>(null);
    drop(ref);
    drag(dragRef);

    return (
        <div ref={ref}
            style={{ opacity: isDragging ? 0.5 : 1 }}
            data-handler-id={handlerId}
            className="relative group pl-7"
        >
            <div
                ref={dragRef}
                className="absolute top-0 -left-0 w-6 h-6 border rounded cursor-move flex items-center justify-center  group-hover:opacity-100 opacity-0"
            >
                <GripVertical height={16} width={16} className=' text-gray-500' />
            </div>
            {children}
        </div>
    );
};

const ShifuEdit = ({ id }: { id: string }) => {
    const { t } = useTranslation();
    const { profile } = useAuth();
    useEffect(() => {
        if (profile){
            i18n.changeLanguage(profile.language);
        }
    }, [profile]);
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
    } = useShifu();
    const [menuPosition, setMenuPosition] = useState<{
        blockId?: string;
        visible?: boolean;
        x?: number;
        y?: number;
    }>({
        visible: false,
        x: 0,
        y: 0
    });
    const [debugBlockInfo, setDebugBlockInfo] = useState({
        blockId: "",
        visible: false,
    })

    const onAddChapter = () => {
        actions.addChapter({
            parent_id: "",
            id: 'new_chapter',
            name: ``,
            children: [],
            no: "",
            depth: 0,
        });
        setTimeout(() => {
            document.getElementById('new_chapter')?.scrollIntoView({
                behavior: 'smooth',
            });
        }, 800);
    }


    const onShowMenu = (id: string, type: string, e: React.MouseEvent<HTMLDivElement>) => {
        console.log(id, type, e);
        if (type !== 'ai') {
            return;
        }
        const target = e.currentTarget as HTMLElement;
        // 计算相对于div的坐标，页面滚动时，保持相对位置
        const rect = target.getBoundingClientRect();
        const width = target.offsetWidth;
        const x = width + rect.left + 40;
        const y = rect.top;
        if (menuPosition.x == x && menuPosition.y == y) {
            return;
        }
        setMenuPosition({ blockId: id, visible: true, x, y });
    }

    const onHideMenu: MouseEventHandler<HTMLDivElement> = () => {
        // setMenuPosition({ visible: false });
    }

    const onDebugBlock = (id: string) => {
        setDebugBlockInfo({ blockId: id, visible: true });
    }

    const onDebugBlockClose = () => {
        setDebugBlockInfo({ blockId: "", visible: false });
        setMenuPosition({ blockId: "", visible: false });
    }

    const onAddBlock = (index: number, type: BlockType, shifuId: string) => {
        actions.addBlock(index, type, shifuId)
    }

    useEffect(() => {
        actions.loadModels();
        if (id) {
            actions.loadChapters(id);
        }
    }, [id]);

    return (
        <div className="flex flex-col h-screen bg-gray-50 overflow-hidden ">
            <Header />
            <div className="flex-1 container mx-auto flex flex-row  overflow-hidden px-10">
                <div className='p-2 flex flex-col overflow-hidden h-full'>
                    <div className='flex-1 h-full overflow-auto pr-4 w-[240px]'>
                        <ol className=' text-sm'>
                            <OutlineTree
                                items={chapters}
                                onChange={(newChapters) => {
                                    actions.setChapters([...newChapters]);
                                }}
                            />
                        </ol>
                        <Button variant="outline" className='my-2 h-8 sticky bottom-0 left-4 ' size="sm" onClick={onAddChapter}>
                            <Plus />
                            {t('shifu.new_chapter')}
                        </Button>
                    </div>

                </div>

                <div className="flex-1 flex flex-col gap-4 p-8 pl-1 ml-0 overflow-auto relative bg-white text-sm"
                    onScroll={() => {
                        setMenuPosition({ visible: false });
                    }}
                >
                    {
                        isLoading && (
                            <div className="h-40 flex items-center justify-center">
                                <Loading />
                            </div>
                        )
                    }
                    {
                        !isLoading && (
                            <>
                                <DndProvider backend={HTML5Backend}>
                                    {blocks.map((block, index) => (
                                        <DraggableBlock
                                            key={block.properties.block_id}
                                            id={block.properties.block_id}
                                            index={index}
                                            moveBlock={(dragIndex: number, hoverIndex: number) => {
                                                const dragBlock = blocks[dragIndex];
                                                const newBlocks = [...blocks];
                                                newBlocks.splice(dragIndex, 1);
                                                newBlocks.splice(hoverIndex, 0, dragBlock);
                                                actions.setBlocks(newBlocks);
                                                actions.autoSaveBlocks(currentNode!.id, newBlocks, blockContentTypes, blockContentProperties, blockUITypes, blockUIProperties, currentShifu?.shifu_id || '')
                                            }}
                                        >
                                            <div id={block.properties.block_id} className="relative flex flex-col gap-2 ">
                                                <div className=' '
                                                    onMouseOver={(e) => onShowMenu(block.properties.block_id, block?.properties?.block_content?.type, e)}
                                                    onMouseLeave={onHideMenu}
                                                >
                                                    <RenderBlockContent
                                                        id={block.properties.block_id}
                                                        type={blockContentTypes[block.properties.block_id]}
                                                        properties={blockContentProperties[block.properties.block_id]}
                                                    />
                                                </div>
                                                <RenderBlockUI block={block} />
                                                <div>
                                                    <AddBlock onAdd={onAddBlock.bind(null, index + 1, "ai", id)} />
                                                </div>
                                            </div>
                                        </DraggableBlock>
                                    ))}
                                </DndProvider>
                                {
                                    ((currentNode?.depth || 0) > 0 && blocks.length === 0) && (
                                        <div className='flex flex-row items-center justify-start h-6 pl-8'>
                                            <AddBlock onAdd={onAddBlock.bind(null, 0, "ai", id)} />
                                        </div>
                                    )
                                }
                            </>

                        )
                    }

                </div>

            </div>
            {
                debugBlockInfo.visible && (
                    <AIDebugDialog blockId={debugBlockInfo.blockId} open={true} onOpenChange={onDebugBlockClose} />
                )
            }

            {
                menuPosition.visible && (
                    <div
                        className=' fixed bg-white hover:bg-gray-100 cursor-pointer rounded-sm h-6 w-6 flex items-center justify-center top-0 -right-16 p-2'
                        style={{
                            top: menuPosition.y + 'px',
                            left: menuPosition.x + 'px',
                            zIndex: 50,
                        }}
                    >

                        <DropdownMenu modal={false} >
                            <DropdownMenuTrigger>
                                <ChevronsRight className='h-4 w-4 shrink-0' />
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align='start' side='bottom' alignOffset={-5}>
                                <DropdownMenuItem onClick={onDebugBlock.bind(null, menuPosition.blockId || "")}>
                                    <Variable />{t('shifu.debug')}
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>
                )
            }
        </div>
    );
};

export default ShifuEdit;

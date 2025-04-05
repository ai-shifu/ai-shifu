/* eslint-disable @typescript-eslint/no-unused-vars */
"use client"
import React, { useState, useEffect, MouseEventHandler } from 'react';
import { Button } from '@/components/ui/button';
import { ChevronsRight, Play, Plus, Variable, } from 'lucide-react';
import { useScenario } from '@/store';
import OutlineTree from '@/components/outline-tree'
import '@mdxeditor/editor/style.css'
import Header from '../header';
import { BlockType } from '@/types/scenario';
import { Separator } from '../ui/separator';
import RenderBlockContent from '../render-block';
import RenderBlockUI from '../render-ui';
import AIDebugDialog from '@/components/ai-debug';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../ui/dropdown-menu';
import AddBlock from '@/components/add-block';

const ScriptEditor = ({ id }: { id: string }) => {
    const {
        blocks,
        chapters,
        actions,
        blockContentTypes,
        blockContentProperties,
        blockUIProperties,
        currentOutline
    } = useScenario();
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
    }
    const onAddSubChapter = () => {
        // actions.createChapter({
        //     outline_id: uuidv4(),
        //     outline_name: `新章节`,
        //     outline_children: [],
        //     outline_no: "",
        //     parent_id: parentChapter.outline_id
        // });
    }

    // const onContentTypeChange = (id: string, type: string) => {
    //     const opt = ContentTypes.find(p => p.type === type);
    //     actions.setBlockContentTypesById(id, type)
    //     actions.setBlockContentPropertiesById(id, opt?.properties || {})
    // }

    const onShowMenu = (id: string, type: string, e) => {
        if (type !== 'ai') {
            return;
        }
        const target = e.currentTarget;
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

    const onAddBlock = (index: number, type: BlockType) => {
        console.log(index, type)
        actions.addBlock(index, type)
    }

    useEffect(() => {
        actions.loadChapters(id);
    }, [id]);

    // useEffect(() => {
    //     actions.autoSaveBlocks(currentOutline)
    // }, [blockContentProperties, blockUIProperties, currentOutline])

    return (
        <div className="flex flex-col h-screen bg-gray-50 overflow-hidden ">
            <Header />
            <div className="flex-1 container mx-auto flex flex-row  overflow-hidden px-10">
                <div className='p-2 flex flex-col overflow-hidden h-full'>
                    <div className="flex items-center py-2">
                        <h3 className="font-semibold">剧本标题</h3>
                    </div>
                    <Separator className="mb-4" />
                    <div className='flex-1 overflow-auto pr-4 w-[240px]'>
                        <ol className=' text-sm'>
                            <OutlineTree
                                items={chapters}
                                // currentChapter={currentChapter}
                                // onChapterClick={scrollToChapter}
                                onAddNodeClick={onAddSubChapter}
                                onChange={(newChapters) => {
                                    // Update chapters with new order by saving each chapter with updated index
                                    // newChapters.forEach((chapter, index) => {
                                    //     actions.saveChapter({
                                    //         ...chapter,
                                    //         chapter_index: index
                                    //     });
                                    // });
                                    actions.setChapters([...newChapters]);
                                }}
                            />
                        </ol>
                        {/* <Input className='h-8'></Input> */}
                        <Button variant="outline" className='my-2 h-8' size="sm" onClick={onAddChapter}>
                            <Plus />
                            新篇章
                        </Button>
                    </div>

                </div>

                <div className="flex-1 flex flex-col gap-8 p-8 ml-0 overflow-auto relative bg-white text-sm "

                    onScroll={() => {
                        setMenuPosition({ visible: false });
                    }}
                >

                    {blocks.map((block, index) => (
                        <div key={block.properties.block_id} className=" relative flex flex-col gap-2 ">
                            <div className=' '
                                onMouseOver={onShowMenu.bind(null, block.properties.block_id, block?.properties?.block_content?.type)}
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
                                <AddBlock onAdd={onAddBlock.bind(null, index + 1)} />
                            </div>
                        </div>
                    ))}
                    {
                        blocks.length === 0 && (
                            <div className='flex flex-row items-center justify-start h-6'>
                                <AddBlock onAdd={onAddBlock.bind(null, 0)} />
                            </div>
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
                            zIndex: 9999,
                        }}
                    >

                        <DropdownMenu>
                            <DropdownMenuTrigger>
                                <ChevronsRight className='h-4 w-4 shrink-0' />
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align='start' side='bottom' alignOffset={-5}>
                                <DropdownMenuItem onClick={onDebugBlock.bind(null, menuPosition.blockId || "")}>
                                    <Variable />测试本模块
                                </DropdownMenuItem>
                                <DropdownMenuItem>
                                    <Play />从当前预览
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>
                )
            }
        </div>
    );
};

export default ScriptEditor;

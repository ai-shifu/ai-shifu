"use client"
import React, { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Check, Plus, Scroll, Trash } from 'lucide-react';
import { useScenario } from '@/store';
import { Input } from '../ui/input';
import OutlineTree from '@/components/outline-tree'
import '@mdxeditor/editor/style.css'
import Header from '../header';
import { Outline } from '@/types/scenario';
import { Separator } from '../ui/separator';
import { v4 as uuidv4 } from 'uuid';
import RenderBlockContent, { ContentTypes } from '../render-block';
import RenderBlockUI, { UITypes } from '../render-ui';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select';

// 简化版Markdown编辑器组件
const MarkdownEditor = ({ content, onChange }: { content: string, onChange: (value: string) => void }) => {
    return (
        <div className="w-full border rounded-md">
            {/* <MDXEditor
                plugins={ALL_PLUGINS}
                markdown={content}
                onChange={onChange}
            /> */}
            <textarea
                defaultValue={content}
                onChange={(e) => onChange(e.target.value)}
                className="w-full p-4 min-h-48 focus:outline-none font-mono text-sm"
                placeholder="在此输入Markdown内容..."
            />
        </div>
    );
};


const ScriptEditor = ({ id }: { id: string }) => {
    const {
        blocks,
        chapters, currentChapter,
        actions, lastSaveTime,
        blockUITypes,
        blockUIProperties,
        blockContentTypes,
        blockContentProperties
    } = useScenario();
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const chapterRefs = useRef<{ [key: string]: HTMLDivElement }>({});

    // 处理内容更新
    const handleContentChange = (newContent: string) => {
        // if (currentChapter) {
        //     actions.saveChapter({
        //         ...currentChapter,
        //         chapter_description: newContent
        //     });
        // }
    };

    const handleNameChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        // if (currentChapter) {
        //     actions.saveChapter({
        //         ...currentChapter,
        //         outline_name: event.target.value
        //     });
        // }
    }

    // 添加新章节
    const handleAddChapter = async (afterChapter: Outline, index: number) => {
        console.log(afterChapter, index)
        // const newChapterIndex = afterChapter.outline_id + 1;
        // await actions.createChapter({
        //     chapter_index: index,
        //     outline_name: `新章节`,
        //     chapter_description: `# 新章节 \n\n请在此处输入内容...`,
        //     scenario_id: id
        // });
    };

    // 滚动到章节
    // const scrollToChapter = (chapter: Outline) => {
    //     if (chapterRefs.current[chapter.outline_id]) {
    //         chapterRefs.current[chapter.outline_id].scrollIntoView({ behavior: 'smooth' });
    //         actions.setCurrentChapter(chapter);
    //     }
    // };

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
    const onAddSubChapter = (parentChapter: Outline) => {
        // actions.createChapter({
        //     outline_id: uuidv4(),
        //     outline_name: `新章节`,
        //     outline_children: [],
        //     outline_no: "",
        //     parent_id: parentChapter.outline_id
        // });
    }

    const onUITypeChange = (id: string, type: string) => {
        const opt = UITypes.find(p => p.type === type);
        actions.setBlockUITypesById(id, type)
        actions.setBlockUIPropertiesById(id, opt?.properties || {})
    }
    const onContentTypeChange = (id: string, type: string) => {
        const opt = ContentTypes.find(p => p.type === type);
        actions.setBlockContentTypesById(id, type)
        actions.setBlockContentPropertiesById(id, opt?.properties || {})
    }

    useEffect(() => {

        actions.loadChapters(id);
    }, [id]);

    return (
        <div className="flex flex-col h-screen bg-gray-50 overflow-hidden ">
            <Header />
            <div className="flex-1 container mx-auto flex flex-row  overflow-hidden">
                <div className='p-2 flex flex-col overflow-hidden h-full'>
                    <div className="flex items-center py-2">
                        <Scroll size={18} className="mr-2" />
                        <h3 className="font-semibold">剧本章节</h3>
                    </div>
                    <Separator className="mb-4" />
                    <div className='flex-1 overflow-auto pr-4'>
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

                <div className="flex-1 flex flex-col gap-8 p-4 ml-0 overflow-auto bg-white text-sm ">
                    {blocks.map((block) => (
                        <div key={block.properties.block_id} className="flex flex-col gap-2 ">
                            <div className='bg-[#F5F5F4] rounded-md p-2'>
                                <div className='flex flex-row items-center py-1 justify-between'>
                                    <Select
                                        value={blockContentTypes[block.properties.block_id]}
                                        onValueChange={onContentTypeChange.bind(null, block.properties.block_id)}
                                    >
                                        <SelectTrigger className="h-8 w-[120px]">
                                            <SelectValue placeholder="请选择" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectGroup>
                                                {
                                                    ContentTypes.map((item) => {
                                                        return (
                                                            <SelectItem key={item.type} value={item.type}>{item.name}</SelectItem>
                                                        )
                                                    })
                                                }
                                            </SelectGroup>
                                        </SelectContent>
                                    </Select>
                                    <div className='flex flex-row'>
                                        <div className='flex flex-row items-center w-6'>
                                            <Trash className='h-5 w-5' />
                                        </div>
                                        <Button variant='ghost' >
                                            <Check />完成
                                        </Button>
                                    </div>
                                </div>
                                <RenderBlockContent
                                    id={block.properties.block_id}
                                    type={blockContentTypes[block.properties.block_id]}
                                    properties={blockContentProperties[block.properties.block_id]}
                                />
                            </div>
                            <div className='bg-[#F5F5F4] rounded-md p-2 space-y-1'>
                                <div className=' flex flex-row items-center space-x-1'>
                                    <span>
                                        用户操作：
                                    </span>
                                    <Select value={blockUITypes[block.properties.block_id]} onValueChange={onUITypeChange.bind(null, block.properties.block_id)}>
                                        <SelectTrigger className=" h-8 w-[120px]">
                                            <SelectValue placeholder="请选择" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectGroup>
                                                {
                                                    UITypes.map((item) => {
                                                        return (
                                                            <SelectItem key={item.type} value={item.type}>{item.name}</SelectItem>
                                                        )
                                                    })
                                                }
                                            </SelectGroup>
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div>
                                    {
                                        blockUIProperties[block.properties.block_id] && (
                                            <RenderBlockUI
                                                id={block.properties.block_id}
                                                type={blockUITypes[block.properties.block_id]}
                                                properties={blockUIProperties[block.properties.block_id]}
                                            />
                                        )
                                    }
                                </div>
                            </div>

                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default ScriptEditor;

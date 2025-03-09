"use client"
import React, { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Plus, Scroll } from 'lucide-react';
import { useScenario } from '@/store';
import { Input } from '../ui/input';
import OutlineTree from '@/components/outline-tree'
import '@mdxeditor/editor/style.css'
import Header from '../header';
import { Outline } from '@/types/scenario';
import { Separator } from '../ui/separator';
import { v4 as uuidv4 } from 'uuid';
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
    const { chapters, currentChapter, actions, lastSaveTime } = useScenario();
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
            id: uuidv4(),
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

                <div className="flex-1 flex flex-col gap-8 px-4 ml-0 ">
                    {chapters.map((chapter, index) => (
                        <div key={chapter.id} onClick={() => actions.setCurrentChapter(chapter)}>
                            <div
                                ref={el => {
                                    if (el) {
                                        chapterRefs.current[chapter.id] = el;
                                    }
                                }}
                                id={`chapter-${chapter.id}`}
                                className={`p-6 bg-white rounded-lg shadow-sm ${currentChapter?.id === chapter.id ? 'ring-2 ring-primary' : ''}`}
                            >
                                <h2 className="text-xl font-semibold mb-4">
                                    <Input defaultValue={chapter.name} onChange={handleNameChange} />
                                </h2>
                                <MarkdownEditor
                                    content={chapter.name}
                                    onChange={handleContentChange}
                                />
                            </div>

                            <div className="flex justify-center my-4">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="flex items-center gap-1"
                                    onClick={() => handleAddChapter(chapter, index)}
                                >
                                    <Plus size={16} />
                                    在此处插入新章节
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default ScriptEditor;

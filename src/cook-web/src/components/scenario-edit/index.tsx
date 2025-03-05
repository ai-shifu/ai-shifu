"use client"
import React, { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Plus, ChevronLeft, ChevronRight } from 'lucide-react';
import { useScenario } from '@/store';
import { Chapter } from '@/types/scenario';
import { Input } from '../ui/input';
import '@mdxeditor/editor/style.css'

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

import ChapterNav from '../chapter-nav';

const ScriptEditor = ({ id }: { id: string }) => {
    const { chapters, currentChapter, actions, lastSaveTime } = useScenario();
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const chapterRefs = useRef<{ [key: string]: HTMLDivElement }>({});

    // 处理内容更新
    const handleContentChange = (newContent: string) => {
        if (currentChapter) {
            actions.saveChapter({
                ...currentChapter,
                chapter_description: newContent
            });
        }
    };

    const handleNameChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        if (currentChapter) {
            actions.saveChapter({
                ...currentChapter,
                chapter_name: event.target.value
            });
        }
    }

    // 添加新章节
    const handleAddChapter = async (afterChapter: Chapter, index: number) => {
        // const newChapterIndex = afterChapter.chapter_id + 1;
        await actions.createChapter({
            chapter_index: index,
            chapter_name: `新章节`,
            chapter_description: `# 新章节 \n\n请在此处输入内容...`,
            scenario_id: id
        });
    };

    // 滚动到章节
    const scrollToChapter = (chapter: Chapter) => {
        if (chapterRefs.current[chapter.chapter_id]) {
            chapterRefs.current[chapter.chapter_id].scrollIntoView({ behavior: 'smooth' });
            actions.setCurrentChapter(chapter);
        }
    };

    useEffect(() => {
        debugger;
        actions.loadChapters(id);
    }, [id]);

    return (
        <div className="min-h-screen bg-gray-50 py-8">
            <div className="container mx-auto">
                <header className="mb-8 px-4 flex justify-between items-center">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                        >
                            {isSidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
                            {isSidebarOpen ? "隐藏章节" : "显示章节"}
                        </Button>
                        {lastSaveTime && (
                            <span className="text-sm text-gray-500">
                                上次保存: {lastSaveTime.toLocaleTimeString()}
                            </span>
                        )}
                    </div>
                </header>

                {isSidebarOpen && (
                    <ChapterNav
                        chapters={chapters}
                        currentChapter={currentChapter}
                        onChapterClick={scrollToChapter}
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
                )}

                <div className="flex flex-col gap-8 px-4 ml-0 md:ml-64">
                    {chapters.map((chapter, index) => (
                        <div key={chapter.chapter_id} onClick={() => actions.setCurrentChapter(chapter)}>
                            <div
                                ref={el => {
                                    if (el) {
                                        chapterRefs.current[chapter.chapter_id] = el;
                                    }
                                }}
                                id={`chapter-${chapter.chapter_id}`}
                                className={`p-6 bg-white rounded-lg shadow-sm ${currentChapter?.chapter_id === chapter.chapter_id ? 'ring-2 ring-primary' : ''}`}
                            >
                                <h2 className="text-xl font-semibold mb-4">
                                    <Input defaultValue={chapter.chapter_name} onChange={handleNameChange} />
                                </h2>
                                <MarkdownEditor
                                    content={chapter.chapter_description}
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
                    {
                        chapters.length == 0 && (
                            <div className="flex justify-center my-4">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="flex items-center gap-1"
                                    onClick={() => handleAddChapter({
                                        chapter_description: '章节内容a',
                                        chapter_id: "",
                                        chapter_name: '新章节a',
                                        scenario_id: ''
                                    }, 0)}
                                >
                                    <Plus size={16} />
                                    在此处插入新章节
                                </Button>
                            </div>
                        )
                    }
                </div>
            </div>
        </div>
    );
};

export default ScriptEditor;

"use client"
import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Scroll, GripVertical } from 'lucide-react';
import { DndProvider, useDrag, useDrop, } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { Outline } from '@/types/scenario';

interface ChapterNavProps {
    chapters: Outline[];
    currentChapter: Outline | null;
    onChapterClick: (chapter: Outline) => void;
    onChange?: (chapters: Outline[]) => void;
}

interface DraggableChapterProps {
    chapter: Outline;
    index: number;
    currentChapter: Outline | null;
    onChapterClick: (chapter: Outline) => void;
    moveChapter: (dragIndex: number, hoverIndex: number, isDragEnd?: boolean) => void;
}

const DraggableChapter = ({ chapter, index, currentChapter, onChapterClick, moveChapter }: DraggableChapterProps) => {
    const [{ isDragging }, drag] = useDrag({
        type: 'CHAPTER',
        item: { index },
        collect: (monitor) => ({
            isDragging: monitor.isDragging(),
        }),
        end: (item, monitor) => {
            if (monitor.didDrop()) {
                moveChapter(item.index, index, true);
            }
        }
    });

    const [, drop] = useDrop({
        accept: 'CHAPTER',
        hover: (item: { index: number }) => {
            if (item.index !== index) {
                moveChapter(item.index, index);
                item.index = index;
            }
        },
    });

    return (
        <div ref={(node) => {
            const dropTarget = drop(node);
            drag(dropTarget);
        }} style={{ opacity: isDragging ? 0.5 : 1 }}>
            <Button
                variant={currentChapter?.outline_id === chapter.outline_id ? "secondary" : "ghost"}
                className="w-full justify-start text-left font-normal group"
                onClick={() => onChapterClick(chapter)}
            >
                <GripVertical size={16} className="mr-2 text-gray-400 group-hover:text-gray-600" />
                {chapter.outline_name}
            </Button>
        </div>
    );
};

const ChapterNav = ({ chapters, currentChapter, onChapterClick, onChange }: ChapterNavProps) => {
    const [chapterList, setChapterList] = React.useState(chapters);

    React.useEffect(() => {
        setChapterList(chapters);
    }, [chapters]);

    const moveChapter = React.useCallback((dragIndex: number, hoverIndex: number, isDragEnd: boolean = false) => {
        const newChapters = [...chapterList];
        const draggedChapter = newChapters[dragIndex];
        newChapters.splice(dragIndex, 1);
        newChapters.splice(hoverIndex, 0, draggedChapter);
        setChapterList(newChapters);

        // Only trigger onChange when drag ends
        if (isDragEnd) {
            onChange?.(newChapters);
        }
    }, [chapterList, onChange]);

    return (
        <DndProvider backend={HTML5Backend}>
            <div className=" w-60 ">
                <div className="p-4">
                    <div className="flex items-center mb-4">
                        <Scroll size={18} className="mr-2" />
                        <h3 className="font-semibold">剧本章节</h3>
                    </div>
                    <Separator className="mb-4" />
                    <ul className="space-y-2">
                        {chapterList.map((chapter, index) => (
                            <li key={chapter.outline_id}>
                                <DraggableChapter
                                    chapter={chapter}
                                    index={index}
                                    currentChapter={currentChapter}
                                    onChapterClick={onChapterClick}
                                    moveChapter={moveChapter}
                                />
                            </li>
                        ))}
                    </ul>
                </div>
            </div>
        </DndProvider>
    );
};

export default ChapterNav;

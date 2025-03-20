/* eslint-disable @next/next/no-img-element */
"use client"
import React from 'react';
import { ChevronLeft, MoreHorizontal, AlignJustify, Book, Settings, Terminal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { useRouter } from 'next/navigation';
import { useScenario } from '@/store';
import Loading from '../loading';


const Header = () => {
    const router = useRouter();
    const { isSaving, lastSaveTime } = useScenario();
    return (
        <div className="flex items-center w-full h-12 px-2 bg-white border-b border-gray-200">
            <div className="flex items-center space-x-4">
                <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => router.back()}>
                    <ChevronLeft className="h-5 w-5" />
                </Button>

                {/* <div className="flex items-center">
                    <div className="bg-blue-100 rounded-md p-1 mr-2">
                        <img
                            src="/api/placeholder/24/24"
                            alt="Profile"
                            className="h-6 w-6 rounded"
                        />
                    </div>
                    <div className="flex items-center">
                        <span className="font-medium text-sm">当前副本的名称</span>
                        <span className="ml-1">
                            <svg className="h-5 w-5 text-green-500" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <circle cx="12" cy="12" r="10" fill="currentColor" fillOpacity="0.2" />
                                <path d="M8 12L11 15L16 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                        </span>
                    </div>
                </div> */}
            </div>

            <div className="flex flex-row items-center text-xs text-gray-500 ml-4">
                {
                    isSaving && (
                        <Loading className='h-4 w-4 mr-1' />
                    )
                }
                {
                    (!isSaving && lastSaveTime) && (
                        <span>
                            已自动保存 {lastSaveTime?.toLocaleString()}
                        </span>
                    )
                }

            </div>
            <div className='flex-1'>

            </div>
            {/* <div className="flex flex-1 ml-auto justify-center items-center space-x-1">
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-8 text-xs font-normal">
                            <AlignJustify className="h-4 w-4 mr-1" />
                            <span>01- 用 AI 编程做什么</span>
                            <ChevronLeft className="h-4 w-4 ml-1 rotate-270" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        <DropdownMenuItem>选项 1</DropdownMenuItem>
                        <DropdownMenuItem>选项 2</DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>

                <Button variant="ghost" className="h-9">
                    <Book className="h-5 w-5" />
                    知识库
                </Button>

                <Button variant="ghost" className="h-9 w-auto">
                    <Settings className="h-5 w-5" />
                    课程设置
                </Button>

                <Sheet>
                    <SheetTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-9 w-9">
                            <MoreHorizontal className="h-5 w-5" />
                        </Button>
                    </SheetTrigger>
                    <SheetContent>
                        <div className="p-4">
                            <h3 className="font-medium mb-2">更多选项</h3>
                            <ul className="space-y-2">
                                <li className="flex items-center">
                                    <Terminal className="h-4 w-4 mr-2" />
                                    <span>命令面板</span>
                                </li>
                                <li className="flex items-center">
                                    <Settings className="h-4 w-4 mr-2" />
                                    <span>设置</span>
                                </li>
                            </ul>
                        </div>
                    </SheetContent>
                </Sheet>


            </div> */}
            <div >
                <Button variant="ghost" size="sm" className="h-8 px-2 text-xs font-normal">
                    [x] 克隆
                </Button>

                <Button size="sm" className="h-8 ml-1 bg-purple-600 hover:bg-purple-700 text-xs font-normal">
                    运行
                </Button>
            </div>
        </div>
    );
};

export default Header;

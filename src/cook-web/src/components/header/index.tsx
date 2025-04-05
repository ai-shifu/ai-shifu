/* eslint-disable @next/next/no-img-element */
"use client"
import React, { useState } from 'react';
import { ArrowTrendingUpIcon, ChevronLeftIcon, AdjustmentsVerticalIcon } from "@heroicons/react/24/outline"
import { Button } from '@/components/ui/button';
import { useRouter } from 'next/navigation';
import { useScenario } from '@/store';
import Loading from '../loading';
import { useAlert } from '@/components/ui/use-alert';
import api from '@/api'
import { CircleAlert, CircleCheck } from 'lucide-react';
import Preivew from '@/components/preview';

const Header = () => {
    const alert = useAlert();
    const router = useRouter();
    const [publishing, setPublishing] = useState(false)
    const { isSaving, lastSaveTime, currentScenario, error } = useScenario();
    const publish = async () => {
        // TODO: publish
        // actions.publishScenario();
        alert.showAlert({
            confirmText: '确认',
            cancelText: '取消',
            title: '是否确认发布',
            description: '发布将会把当前内容更新上线，请确认后再发布！',
            async onConfirm() {
                setPublishing(true)
                const reuslt = await api.publishScenario({
                    scenario_id: currentScenario?.id || ''
                });
                setPublishing(false)
                alert.showAlert({
                    title: '发布成功',
                    confirmText: '去查看',
                    cancelText: '关闭',
                    description: (
                        <div className="flex flex-col space-y-2">
                            <span>发布成功，请前往查看</span>
                            <a href={reuslt} target="_blank" rel="noreferrer" className="text-blue-500 hover:underline">
                                {reuslt}
                            </a>
                        </div >
                    ),
                    onConfirm() {
                        window.open(reuslt, '_blank');
                    }
                })
            },
        })
    }
    return (
        <div className="flex items-center w-full h-12 px-2 bg-white border-b border-gray-200">
            <div className="flex items-center space-x-4">
                <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => router.back()}>
                    <ChevronLeftIcon className="h-5 w-5" />
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
                    !error && (!isSaving && lastSaveTime) && (
                        <span className='flex flex-row items-center'>
                            <CircleCheck height={18} width={18} className='mr-1  text-primary' />  已自动保存 {lastSaveTime?.toLocaleString()}
                        </span>
                    )
                }
                {
                    error && (
                        <span className='flex flex-row items-center text-red-500'>
                            <CircleAlert height={18} width={18} className='mr-1' />  {error}
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
            <div className='flex flex-row items-center'>
                <Button variant="ghost" size="sm">
                    <AdjustmentsVerticalIcon /> 设置
                </Button>


                <Preivew />

                <Button size="sm" className="h-8 ml-1 bg-purple-600 hover:bg-purple-700 text-xs font-normal"
                    onClick={publish}
                >
                    {
                        publishing && (
                            <Loading className='h-4 w-4 mr-1' />
                        )
                    }
                    {
                        !publishing && (
                            <ArrowTrendingUpIcon />
                        )
                    }
                    发布
                </Button>
            </div>
        </div>
    );
};

export default Header;

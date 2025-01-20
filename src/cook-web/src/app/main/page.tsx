"use client"

import React, { useState } from 'react';
import { PlusIcon, BoltIcon, StarIcon as StarOutlineIcon, RectangleStackIcon as RectangleStackOutlineIcon } from '@heroicons/react/24/outline';
import { TrophyIcon, AcademicCapIcon, UserIcon, MusicalNoteIcon, RectangleStackIcon, StarIcon } from '@heroicons/react/24/solid';
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ScriptCard = ({ icon: Icon, title }: any) => (
    <Card className="w-full md:w-[calc(50%-1rem)] lg:w-[calc(33.33%-1rem)] rounded-xl bg-background hover:scale-105 transition-all duration-200 ease-in-out">
        <CardContent className="p-4">
            <div className='flex flex-row items-center'>
                <div className="p-2 h-10 w-10 rounded-lg bg-purple-50 mr-4 mb-3">
                    <Icon className="w-6 h-6 text-purple-600" />
                </div>
                <h3 className="font-medium text-gray-900 leading-5">{title}</h3>
            </div>
            <div className=" ">
                <p className="mt-1 text-sm text-gray-500">
                    剧本简述可能更长剧本简述可能更长，剧本简述可能更长剧本简述可能更长，剧本简述可能更长剧本简述可能更长。
                </p>
                <p className="mt-1 text-sm text-gray-500">
                    剧本简述可能更长剧本简述可能更长，剧本简述可能更长剧本简述可能更长，剧本简述可能更长剧本简述可能更长。
                </p>
            </div>
        </CardContent>
    </Card>
);

const ScriptManagementPage = () => {
    const [activeTab, setActiveTab] = useState("all");

    const scripts = [
        { id: 1, icon: TrophyIcon, title: '剧本标题可能会比较长，存在折行的情况', isFavorite: true },
        { id: 2, icon: AcademicCapIcon, title: '剧本标题可能会比较长，存在折行的情况', isFavorite: false },
        { id: 3, icon: UserIcon, title: '剧本标题可能会比较长，存在折行的情况', isFavorite: true },
        { id: 4, icon: MusicalNoteIcon, title: '剧本标题可能会比较长，存在折行的情况', isFavorite: false },
    ];

    const filteredScripts = activeTab === "favorites"
        ? scripts.filter(script => script.isFavorite)
        : scripts;

    return (
        <div className="h-full bg-gray-50 p-0">
            <div className="max-w-7xl mx-auto">
                <div className="flex justify-between items-center mb-5">
                    <h1 className="text-2xl font-semibold text-gray-900">剧本</h1>
                </div>
                <div className="flex space-x-3 mb-5">
                    <Button size='sm' variant="default" className="bg-purple-600 hover:bg-purple-700">
                        <BoltIcon className="w-5 h-5 mr-1" />
                        从模版创建
                    </Button>
                    <Button size='sm' variant="outline">
                        <PlusIcon className="w-5 h-5 mr-1" />
                        新建空白剧本
                    </Button>
                    <Button size='sm' variant="outline">
                        导入
                    </Button>
                </div>
                <Tabs defaultValue="all" className="mb-6" onValueChange={setActiveTab}>
                    <TabsList className='bg-stone-50 px-0'>
                        <TabsTrigger value="all">
                            {
                                activeTab == 'all' && (
                                    <RectangleStackIcon className="w-5 h-5 mr-1 text-primary" />
                                )
                            }
                            {
                                activeTab != 'all' && (
                                    <RectangleStackOutlineIcon className="w-5 h-5 mr-1" />
                                )
                            }
                            全部
                        </TabsTrigger>
                        <TabsTrigger value="favorites">
                            {
                                activeTab == 'favorites' && (
                                    <StarIcon className="w-5 h-5 mr-1 text-primary" />
                                )
                            }
                            {
                                activeTab != 'favorites' && (
                                    <StarOutlineIcon className="w-5 h-5 mr-1" />
                                )
                            }
                            收藏
                        </TabsTrigger>
                    </TabsList>
                    <TabsContent value="all">
                        <div className="flex flex-wrap gap-4">
                            {filteredScripts.map((script) => (
                                <ScriptCard
                                    key={script.id}
                                    icon={script.icon}
                                    title={script.title}
                                    isFavorite={script.isFavorite}
                                />
                            ))}
                        </div>
                    </TabsContent>
                    <TabsContent value="favorites">
                        <div className="flex flex-wrap gap-4">
                            {filteredScripts.map((script) => (
                                <ScriptCard
                                    key={script.id}
                                    icon={script.icon}
                                    title={script.title}
                                    isFavorite={script.isFavorite}
                                />
                            ))}
                        </div>
                    </TabsContent>
                </Tabs>
            </div>
        </div>
    );
};

export default ScriptManagementPage;

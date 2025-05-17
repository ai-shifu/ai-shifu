"use client"

import React, { useState, useRef, useEffect } from 'react';
import { PlusIcon, StarIcon as StarOutlineIcon, RectangleStackIcon as RectangleStackOutlineIcon } from '@heroicons/react/24/outline';
import { TrophyIcon, RectangleStackIcon, StarIcon } from '@heroicons/react/24/solid';
import api from "@/api";
import { Shifu } from '@/types/shifu';
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CreateShifuDialog } from "@/components/create-shifu-dialog";
import { useToast } from "@/hooks/use-toast";
import { useRouter } from 'next/navigation';
import Loading from '@/components/loading';
import { useTranslation } from 'react-i18next';
interface ShifuCardProps {
    id: string;
    image: string | undefined;
    title: string;
    description: string;
    isFavorite: boolean;
}

const ShifuCard = ({ id, image, title, description, isFavorite }: ShifuCardProps) => {
    const router = useRouter()
    return (
        <Card className="w-full md:w-[calc(50%-1rem)] lg:w-[calc(33.33%-1rem)] cursor-pointer rounded-xl bg-background hover:scale-105 transition-all duration-200 ease-in-out"
            onClick={() => router.push(`/shifu/${id}`)}
        >
            <CardContent className="p-4 cursor-pointer" >
                <div className='flex flex-row items-center justify-between'>
                    <div className='flex flex-row items-center mb-2'>
                        <div className="p-2 h-10 w-10 rounded-lg bg-purple-50 mr-4 flex items-center justify-center shrink-0">
                            {
                                image && <img src={image} alt="recipe" className="w-full h-full object-cover rounded-lg" />
                            }
                            {
                                !image && <TrophyIcon className="w-6 h-6 text-purple-600" />
                            }
                        </div>

                        <h3 className="font-medium text-gray-900 leading-5">{title}</h3>
                    </div>
                    {isFavorite && (
                        <StarIcon className="w-5 h-5 text-yellow-400" />
                    )}
                </div>
                <div>
                    <p className="mt-1 text-sm text-gray-500 line-clamp-3">
                        {description}
                    </p>
                </div>
            </CardContent>
        </Card >
    );
}

const ScriptManagementPage = () => {

    const { toast } = useToast();
    const { t } = useTranslation();
    const [activeTab, setActiveTab] = useState("all");
    const [shifus, setShifus] = useState<Shifu[]>([]);
    const [loading, setLoading] = useState(false);
    const [hasMore, setHasMore] = useState(true);
    const [showCreateShifuModal, setShowCreateShifuModal] = useState(false);
    const pageSize = 30;
    const currentPage = useRef(1);
    const containerRef = useRef(null);

    const fetchShifus = async () => {
        if (loading || !hasMore) return;

        setLoading(true);
        try {

            const { items } = await api.getShifuList({
                page_index: currentPage.current,
                page_size: pageSize,
                is_favorite: activeTab === "favorites",
            });
            if (items.length < pageSize) {
                setHasMore(false);
            }

            setShifus(prev => [...prev, ...items]);
            currentPage.current += 1;
            setLoading(false);
        } catch (error) {
            console.error("Failed to fetch shifus:", error);
        }
    };
    const onCreateShifu = async (values: any) => {
        try {
            await api.createShifu(values);
            toast({
                title: t('common.create-success'),
                description: t('common.create-success-description'),
            });
            setShifus([]);
            setHasMore(true);
            currentPage.current = 1;
            fetchShifus();
            setShowCreateShifuModal(false);
        } catch (error) {
            toast({
                title: t('common.create-failed'),
                description: error instanceof Error ? error.message : t('common.unknown-error'),
                variant: "destructive",
            });
        }
    }

    const handleCreateShifuModal = () => setShowCreateShifuModal(true);

    useEffect(() => {
        setShifus([]);
        setHasMore(true);
        currentPage.current = 1;
    }, [activeTab]);

    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting && hasMore) {
                    fetchShifus();
                }
            },
            { threshold: 0.1 }
        );

        observer.observe(container);
        return () => observer.disconnect();
    }, [hasMore]);


    return (
        <div className="h-full bg-gray-50 p-0">
            <div className="max-w-7xl mx-auto h-full overflow-hidden flex flex-col">
                <div className="flex justify-between items-center mb-5">
                    <h1 className="text-2xl font-semibold text-gray-900">{t('common.shifu')}</h1>
                </div>
                <div className="flex space-x-3 mb-5">
                    <Button size='sm' variant="outline" onClick={handleCreateShifuModal}>
                        <PlusIcon className="w-5 h-5 mr-1" />
                        {t('common.create-blank-shifu')}
                    </Button>
                    <CreateShifuDialog
                        open={showCreateShifuModal}
                        onOpenChange={setShowCreateShifuModal}
                        onSubmit={onCreateShifu}
                    />
                </div>
                <Tabs defaultValue="all" className="mb-0" onValueChange={setActiveTab}>
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
                            {t('common.all')}
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
                            {t('common.favorites')}
                        </TabsTrigger>
                    </TabsList>
                    <TabsContent value="all" className=' flex-1 overflow-auto'>

                    </TabsContent>
                    <TabsContent value="favorites">
                    </TabsContent>

                </Tabs>
                <div className='flex-1 overflow-auto'>
                    <div className="flex flex-wrap gap-4">
                        {shifus.map((shifu) => (
                            <ShifuCard
                                id={shifu.shifu_id + ""}
                                key={shifu.shifu_id}
                                image={shifu.shifu_avatar}
                                title={shifu.shifu_name || ""}
                                description={shifu.shifu_description || ""}
                                isFavorite={shifu.is_favorite || false}
                            />
                        ))}
                    </div>
                    <div
                        ref={containerRef}
                        className="w-full h-10 flex items-center justify-center"
                    >
                        {loading && (
                            <Loading />
                        )}
                        {!hasMore && shifus.length > 0 && (
                            <p className="text-gray-500 text-sm">{t('common.no-more-shifus')}</p>
                        )}
                        {
                            !loading && !hasMore && shifus.length == 0 && (
                                <p className="text-gray-500 text-sm">{t('common.no-shifus')}</p>
                            )
                        }
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ScriptManagementPage;

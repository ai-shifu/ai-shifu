'use client';

import React, { useState, useRef, useEffect } from 'react';
import {
  PlusIcon,
  StarIcon as StarOutlineIcon,
  RectangleStackIcon as RectangleStackOutlineIcon,
} from '@heroicons/react/24/outline';
import {
  TrophyIcon,
  RectangleStackIcon,
  StarIcon,
} from '@heroicons/react/24/solid';
import api from '@/api';
import { Scenario } from '@/types/scenario';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { CreateScenarioDialog } from '@/components/create-scenario-dialog';
import { useToast } from '@/hooks/use-toast';
import { useRouter } from 'next/navigation';
import Loading from '@/components/loading';

interface ScriptCardProps {
  id: string;
  image: string | undefined;
  title: string;
  description: string;
  isFavorite: boolean;
}

const ScriptCard = ({
  id,
  image,
  title,
  description,
  isFavorite,
}: ScriptCardProps) => {
  const router = useRouter();
  return (
    <Card
      className="w-full md:w-[calc(50%-1rem)] lg:w-[calc(33.33%-1rem)] cursor-pointer rounded-xl bg-background hover:scale-105 transition-all duration-200 ease-in-out"
      onClick={() => router.push(`/scenario/${id}`)}
    >
      <CardContent className="p-4 cursor-pointer">
        <div className="flex flex-row items-center justify-between">
          <div className="flex flex-row items-center mb-2">
            <div className="p-2 h-10 w-10 rounded-lg bg-purple-50 mr-4 flex items-center justify-center shrink-0">
              {image && (
                <img
                  src={image}
                  alt="recipe"
                  className="w-full h-full object-cover rounded-lg"
                />
              )}
              {!image && <TrophyIcon className="w-6 h-6 text-purple-600" />}
            </div>

            <h3 className="font-medium text-gray-900 leading-5">{title}</h3>
          </div>
          {isFavorite && <StarIcon className="w-5 h-5 text-yellow-400" />}
        </div>
        <div>
          <p className="mt-1 text-sm text-gray-500 line-clamp-3">
            {description}
          </p>
        </div>
      </CardContent>
    </Card>
  );
};

const ScriptManagementPage = () => {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('all');
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [showCreateScenarioModal, setShowCreateScenarioModal] = useState(false);
  const pageSize = 30;
  const currentPage = useRef(1);
  const containerRef = useRef(null);

  const fetchScenarios = async () => {
    if (loading || !hasMore) return;

    setLoading(true);
    try {
      const { items } = await api.getScenarioList({
        page_index: currentPage.current,
        page_size: pageSize,
        is_favorite: activeTab === 'favorites',
      });
      console.log(items);
      if (items.length < pageSize) {
        setHasMore(false);
      }

      setScenarios((prev) => [...prev, ...items]);
      currentPage.current += 1;
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch scenarios:', error);
    }
  };
  const onCreateScenario = async (values: any) => {
    try {
      await api.createScenario(values);
      toast({
        title: '创建成功',
        description: '新剧本已创建',
      });
      setScenarios([]);
      setHasMore(true);
      currentPage.current = 1;
      fetchScenarios();
      setShowCreateScenarioModal(false);
    } catch (error) {
      toast({
        title: '创建失败',
        description: error instanceof Error ? error.message : '未知错误',
        variant: 'destructive',
      });
    }
  };

  const handleCreateScenarioModal = () => setShowCreateScenarioModal(true);

  useEffect(() => {
    setScenarios([]);
    setHasMore(true);
    currentPage.current = 1;
  }, [activeTab]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore) {
          fetchScenarios();
        }
      },
      { threshold: 0.1 },
    );

    observer.observe(container);
    return () => observer.disconnect();
  }, [hasMore]);

  return (
    <div className="h-full bg-gray-50 p-0">
      <div className="max-w-7xl mx-auto h-full overflow-hidden flex flex-col">
        <div className="flex justify-between items-center mb-5">
          <h1 className="text-2xl font-semibold text-gray-900">剧本</h1>
        </div>
        <div className="flex space-x-3 mb-5">
          <Button
            size="sm"
            variant="outline"
            onClick={handleCreateScenarioModal}
          >
            <PlusIcon className="w-5 h-5 mr-1" />
            新建空白剧本
          </Button>
          <CreateScenarioDialog
            open={showCreateScenarioModal}
            onOpenChange={setShowCreateScenarioModal}
            onSubmit={onCreateScenario}
          />
        </div>
        <Tabs defaultValue="all" className="mb-0" onValueChange={setActiveTab}>
          <TabsList className="bg-stone-50 px-0">
            <TabsTrigger value="all">
              {activeTab == 'all' && (
                <RectangleStackIcon className="w-5 h-5 mr-1 text-primary" />
              )}
              {activeTab != 'all' && (
                <RectangleStackOutlineIcon className="w-5 h-5 mr-1" />
              )}
              全部
            </TabsTrigger>
            <TabsTrigger value="favorites">
              {activeTab == 'favorites' && (
                <StarIcon className="w-5 h-5 mr-1 text-primary" />
              )}
              {activeTab != 'favorites' && (
                <StarOutlineIcon className="w-5 h-5 mr-1" />
              )}
              收藏
            </TabsTrigger>
          </TabsList>
          <TabsContent
            value="all"
            className=" flex-1 overflow-auto"
          ></TabsContent>
          <TabsContent value="favorites"></TabsContent>
        </Tabs>
        <div className="flex-1 overflow-auto">
          <div className="flex flex-wrap gap-4">
            {scenarios.map((scenario) => (
              <ScriptCard
                id={scenario.id + ''}
                key={scenario.id}
                image={scenario.image}
                title={scenario.name || ''}
                description={scenario.description || ''}
                isFavorite={scenario.is_favorite || false}
              />
            ))}
          </div>
          <div
            ref={containerRef}
            className="w-full h-10 flex items-center justify-center"
          >
            {loading && <Loading />}
            {!hasMore && scenarios.length > 0 && (
              <p className="text-gray-500 text-sm">没有更多剧本了</p>
            )}
            {!loading && !hasMore && scenarios.length == 0 && (
              <p className="text-gray-500 text-sm">暂无剧本</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScriptManagementPage;

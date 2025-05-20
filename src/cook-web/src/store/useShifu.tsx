

import { Shifu, ShifuContextType, Outline, Block, ProfileItem, AIBlockProperties, SolidContentBlockProperties } from "../types/shifu";
import api from "@/api";
import { useContentTypes } from "@/components/render-block";
import { useUITypes } from "@/components/render-ui";
import { debounce } from "lodash";
import { createContext, ReactNode, useContext, useState, useCallback } from "react";

const ShifuContext = createContext<ShifuContextType | undefined>(undefined);

const buildBlockListWithAllInfo = (blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>) => {
    const list = blocks.map((block: Block, index) => {
        return {
            "properties": {
                block_id: block.properties.block_id,
                "block_no": "",
                "block_name": "",
                "block_desc": "",
                "block_type": 101,
                "block_index": index,
                "block_content": {
                    type: blockContentTypes[block.properties.block_id],
                    properties: blockContentProperties[block.properties.block_id]
                },
                "block_ui": {
                    type: blockUITypes[block.properties.block_id],
                    properties: blockUIProperties[block.properties.block_id]
                }
            },
            "type": "block"
        }
    })
    return list;
}

export const ShifuProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [currentShifu, setCurrentShifu] = useState<Shifu | null>(null);
    const [chapters, setChapters] = useState<Outline[]>([]);
    const [isSaving, setIsSaving] = useState(false);
    const [lastSaveTime, setLastSaveTime] = useState<Date | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [focusId, setFocusId] = useState('');
    const [focusValue, setFocusValue] = useState('');
    const [cataData, setCataData] = useState<{ [x: string]: Outline }>({})
    const [blocks, setBlocks] = useState<Block[]>([]);
    const [blockContentProperties, setBlockContentProperties] = useState<{ [x: string]: any }>({});
    const [blockContentTypes, setBlockContentTypes] = useState<{ [x: string]: string }>({});
    const [blockUIProperties, setBlockUIProperties] = useState<{ [x: string]: any }>({});
    const [blockUITypes, setBlockUITypes] = useState<{ [x: string]: string }>({});
    const [blockContentState, setBlockContentState] = useState<{ [x: string]: 'edit' | 'preview' }>({});
    const [currentNode, setCurrentNode] = useState<Outline | null>(null);
    const [profileItemDefinations, setProfileItemDefinations] = useState<ProfileItem[]>([]);
    const [models, setModels] = useState<string[]>([]);

    // 确保在客户端环境下获取 UI 类型和内容类型
    const UITypes = useUITypes();
    const ContentTypes = useContentTypes();

    const loadShifu = async (shifuId: string) => {
        try {
            setIsLoading(true);
            setError(null);
            const shifu = await api.getShifuInfo({
                shifu_id: shifuId
            });
            setCurrentShifu(shifu);

        } catch (error) {
            console.error(error);
            setError("Failed to load shifu");
        } finally {
            setIsLoading(false);
        }
    };

    // useEffect(() => {
    //     console.log(currentShifu);
    // }, [currentShifu]);

    const recursiveCataData = (cataTree: Outline[]): any => {
        const result: any = {};
        const processItem = (item: any, parentId = "", depth = 0) => {
            result[item.id] = {
                ...cataData[item.id],
                parend_id: parentId,
                name: item.name,
                depth: depth,
                status: 'edit',
            };

            if (item.children) {
                item.children.forEach((child: any) => {
                    processItem(child, item.id, depth + 1);
                });
            }
        };

        cataTree.forEach((child: any) => {
            processItem(child, "", 0);
        });
        return result;
    }
    const buildOutlineTree = (items: Outline[]) => {
        const treeData = recursiveCataData(items);
        setCataData(treeData);
        return treeData;
    }
    const findNode = (id: string) => {
        const find = (nodes: Outline[]): any => {
            for (let i = 0; i < nodes.length; i++) {
                if (nodes[i].id === id) {
                    return nodes[i];
                }
                if (nodes[i].children) {
                    const result = find(nodes[i].children || []);
                    if (result) {
                        return result;
                    }
                }

            }
            return null;
        }
        return find(chapters);
    }
    const removeOutline = async (outline: Outline) => {
        setIsSaving(true);
        setError(null);
        try {
            if (outline.parentId) {
                const parent = findNode(outline.parentId || "");
                if (parent) {
                    parent.children = parent.children?.filter((child: any) => child.id !== outline.id);
                }

                setChapters([...chapters])

                delete cataData[outline.id];
                setCataData({
                    ...cataData,
                })
                if (outline.id == 'new_chapter') {
                    return;
                }
                if (outline.depth == 0) {
                    await api.deleteChapter({
                        chapter_id: outline.id,
                        shifu_id: currentShifu?.shifu_id || ''
                    })
                } else if (outline.depth == 1) {
                    await api.deleteUnit({
                        unit_id: outline.id,
                        shifu_id: currentShifu?.shifu_id || ''
                    })
                }
            } else {
                const list = chapters.filter((child: any) => child.id !== outline.id);
                setChapters([...list])

                delete cataData[outline.id];
                setCataData({
                    ...cataData,
                })

                if (outline.id == 'new_chapter') {
                    return;
                }
                await api.deleteChapter({
                    chapter_id: outline.id,
                    shifu_id: currentShifu?.shifu_id || ''
                })
            }
            setLastSaveTime(new Date());
        } catch (error) {
            console.error(error);
            setError("Failed to remove outline");
        } finally {
            setIsSaving(false);
        }
    }

    const loadChapters = async (shifuId: string) => {
        try {
            setIsLoading(true);
            setError(null);
            const shifuInfo = await api.getShifuInfo({ shifu_id: shifuId });
            setCurrentShifu(shifuInfo);
            const chaptersData = await api.getShifuOutlineTree({ shifu_id: shifuId });

            const list = chaptersData.map((chapter: any) => {
                return {
                    id: chapter.id,
                    name: chapter.name,
                    children: chapter.children,
                    no: chapter.no,
                }
            })
            if (list.length > 0) {
                if (list[0].children && list[0].children.length > 0) {
                    // setCurrentOutline(list[0].children[0].id);
                    setCurrentNode({
                        ...list[0].children[0],
                        depth: 1,
                    });
                    await loadBlocks(list[0].children[0].id, shifuId);
                }
            }
            setChapters(list);
            buildOutlineTree(list);
            loadProfileItemDefinations(shifuId);
        } catch (error) {
            console.error(error);
            setError("Failed to load chapters");
        } finally {
            setIsLoading(false);
        }
    };
    const initBlockContentTypes = async (list: Block[]) => {
        const types = list.reduce((prev: any, cur: Block) => {
            prev[cur.properties.block_id] = cur.properties.block_content.type;
            return prev;
        }, {});
        setBlockContentTypes(types);
    }

    const initBlockContentProperties = async (list: Block[]) => {
        const properties = list.reduce((prev: any, cur: Block) => {
            return {
                ...prev,
                [cur.properties.block_id]: cur.properties.block_content.properties
            }
        }, {});
        setBlockContentProperties(properties);
    }
    const initBlockUITypes = async (list: Block[]) => {
        const types = list.reduce((prev: any, cur: Block) => {
            prev[cur.properties.block_id] = cur.properties.block_ui.type;
            return prev;
        }, {});
        setBlockUITypes(types);
    }

    const initBlockUIProperties = async (list: Block[]) => {
        const properties = list.reduce((prev: any, cur: Block) => {
            return {
                ...prev,
                [cur.properties.block_id]: cur.properties.block_ui.properties
            }
        }, {});
        setBlockUIProperties(properties);
    }

    const buildBlockList = (blocks: Block[]) => {
        const list = blocks.map((block: Block, index) => {
            return {
                "properties": {
                    block_id: block.properties.block_id,
                    "block_no": "",
                    "block_name": "",
                    "block_desc": "",
                    "block_type": 101,
                    "block_index": index,
                    "block_content": {
                        type: blockContentTypes[block.properties.block_id],
                        properties: blockContentProperties[block.properties.block_id]
                    },
                    "block_ui": {
                        type: blockUITypes[block.properties.block_id],
                        properties: blockUIProperties[block.properties.block_id]
                    }
                },
                "type": "block"
            }
        })
        return list;
    }

    const loadBlocks = async (outlineId: string, shifuId: string) => {
        try {
            setIsLoading(true);
            setError(null);
            const blocksData = await api.getBlocks({ outline_id: outlineId, shifu_id: shifuId });
            const list = blocksData.filter(p => p.type == 'block') as Block[];
            setBlocks(list);
            initBlockContentTypes(list);
            initBlockContentProperties(list);
            const blockUIList = list.filter(p => p.properties.block_ui);
            initBlockUITypes(blockUIList);
            initBlockUIProperties(blockUIList);
            setIsLoading(false);

        } catch (error) {
            console.error(error);
            setError("Failed to load blocks");
            setIsLoading(false);
        }
    }
    const saveBlocks = async (shifu_id: string) => {
        if (isLoading) {
            return;
        }
        const list = buildBlockList(blocks);
        try {
            setError(null);
            await api.saveBlocks({ outline_id: currentNode!.id, blocks: list, shifu_id: shifu_id });
        } catch (error) {
            console.error(error);
            setError("Failed to save blocks");
        }
    }
    const addBlock = async (index: number, blockType: string = 'ai', shifu_id: string) => {
        setIsSaving(true);
        setError(null);
        try {
            const item = ContentTypes.find(p => p.type == blockType);
            const buttonUI = UITypes[0];

            const block = await api.addBlock({
                "block": {
                    "block_content": {
                        type: blockType,
                        properties: item?.properties
                    },
                    "block_desc": "",
                    "block_index": index,
                    "block_name": "",
                    "block_no": "",
                    "block_type": 0,
                    "block_ui": buttonUI
                },
                "block_index": index,
                "outline_id": currentNode!.id,
                "shifu_id": shifu_id,
            });

            blocks.splice(index, 0, block);
            const list = [...blocks];
            setBlockContentTypes({
                ...blockContentTypes,
                [block.properties.block_id]: blockType
            });
            setBlockContentProperties({
                ...blockContentProperties,
                [block.properties.block_id]: item?.properties
            });
            setBlockUITypes({
                ...blockUITypes,
                [block.properties.block_id]: buttonUI.type
            });
            setBlockUIProperties({
                ...blockUIProperties,
                [block.properties.block_id]: buttonUI.properties
            });
            setBlockContentStateById(block.properties.block_id, 'edit');
            setBlocks(list);
            setLastSaveTime(new Date());

            setTimeout(() => {
                document.getElementById(block.properties.block_id)?.scrollIntoView({
                    behavior: 'smooth',
                });
            }, 500);
        } catch (error) {
            console.error(error);
            setError("Failed to add block");
        } finally {
            setIsSaving(false);
        }
    }
    const addSubOutline = async (parent: Outline, name = '') => {
        if (cataData['new_chapter']) {
            return;
        }
        if (parent.children?.find((child: any) => child.id === 'new_chapter')) {
            return;
        }
        const id = 'new_chapter'
        parent.children?.push({
            id,
            parent_id: parent.id,
            name: name,
            children: [],
            no: '',
            depth: (parent?.depth || 0) + 1,
        });

        updateOuline(id, {
            parent_id: parent.id,
            id,
            name: name,
            children: [],
            no: '',
            depth: (parent?.depth || 0) + 1,
        })

        setChapters([...chapters]);

        setFocusId(id);
    }

    const saveCurrentBlocks = useCallback(async (outline: string, blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>, shifu_id: string) => {
        if (isLoading) {
            return;
        }
        setIsSaving(true);
        setError(null);
        try {
            setError(null);
            const blockList = buildBlockListWithAllInfo(blocks, blockContentTypes, blockContentProperties, blockUITypes, blockUIProperties);
            await api.saveBlocks({ outline_id: outline, blocks: blockList, shifu_id: shifu_id || '' });
            setIsSaving(false);
            setLastSaveTime(new Date());
        } catch (error: any) {
            console.error(error);
            setError(error.message);
        } finally {
            setIsSaving(false);
            setLastSaveTime(new Date());
        }
    }, []);

    const autoSaveBlocks = useCallback(debounce((outline: string, blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>, shifu_id: string) => {
        return saveCurrentBlocks(outline, blocks, blockContentTypes, blockContentProperties, blockUITypes, blockUIProperties, shifu_id);
    }, 3000), [saveCurrentBlocks]) as (outline: string, blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>, shifu_id: string) => Promise<void>;


    const addSiblingOutline = async (item: Outline, name = '') => {
        const id = 'new_chapter'
        const parent = findNode(item.parentId || "");
        const index = parent?.children?.findIndex((child: any) => child.id === item.id);
        // insert item after index;
        parent.children?.splice(index + 1, 0, {
            id,
            parent_id: parent.id,
            name: name,
            children: [],
            no: '',
            depth: (parent?.depth || 0) + 1,
        })

        updateOuline(id, {
            parent_id: parent.id,
            id,
            name: name,
            children: [],
            no: '',
            depth: (parent?.depth || 0) + 1,
        })

        setChapters([...chapters]);

        setFocusId(id);
    }

    const createChapter = async (data: Outline) => {
        setIsSaving(true);
        setError(null);
        updateOutlineStatus(data.id, 'saving');
        const index = chapters.findIndex((child) => child.id === data.id);

        try {
            if (data.id === 'new_chapter') {
                const newChapter = await api.createChapter({
                    parent_id: data.parent_id,
                    "chapter_description": data.name,
                    "chapter_index": index,
                    "chapter_name": data.name,
                    "shifu_id": currentShifu?.shifu_id
                });
                replaceOutline('new_chapter', {
                    id: newChapter.chapter_id,
                    name: newChapter.chapter_name,
                    no: '',
                    children: []
                })
                setFocusId("")
                setLastSaveTime(new Date());
            } else {
                await api.modifyChapter({
                    "chapter_id": data.id,
                    "chapter_index": index,
                    "chapter_description": data.name,
                    "chapter_name": data.name,
                    "shifu_id": currentShifu?.shifu_id
                })

                const currentChapter = chapters.find(chapter => chapter.id === data.id);

                replaceOutline(data.id, {
                    id: data.id,
                    name: data.name,
                    no: '',
                    children: currentChapter?.children || []
                })
                setFocusId("")
                setLastSaveTime(new Date());
            }
        } catch (error) {
            console.error(error);
            setError(data.id === 'new_chapter' ? "Failed to create chapter" : "Failed to modify chapter");
            updateOutlineStatus(data.id, data.id === 'new_chapter' ? 'new' : 'edit');
            setFocusId(data.id);
        } finally {
            setIsSaving(false);
            setIsLoading(false);
        }
    };

    const createUnit = async (data: Outline) => {
        setIsSaving(true);
        setError(null);
        updateOutlineStatus(data.id, 'saving');

        const parent = findNode(data.parent_id || "");
        const index = parent.children.findIndex((child) => child.id === data.id);

        try {
            if (data.id === 'new_chapter') {
                const newUnit = await api.createUnit({
                    parent_id: data.parent_id,
                    "unit_index": index,
                    "chapter_id": data.parent_id,
                    "unit_description": data.name,
                    "unit_name": data.name,
                    "shifu_id": currentShifu?.shifu_id
                });

                replaceOutline('new_chapter', {
                    id: newUnit.id,
                    name: newUnit.name,
                    no: '',
                    children: []
                })
                setFocusId("")
                setLastSaveTime(new Date());
            } else {
                await api.modifyUnit({
                    "unit_id": data.id,
                    "unit_index": index,
                    "unit_description": data.name,
                    "unit_name": data.name,
                    "shifu_id": currentShifu?.shifu_id
                })
                replaceOutline(data.id, {
                    id: data.id,
                    name: data.name,
                    no: '',
                    children: []
                })
                setFocusId("")
                setLastSaveTime(new Date());
            }
        } catch (error) {
            console.error(error);
            setError(data.id === 'new_chapter' ? "Failed to create unit" : "Failed to modify unit");
            updateOutlineStatus(data.id, data.id === 'new_chapter' ? 'new' : 'edit');
            setFocusId(data.id);
        } finally {
            setIsSaving(false);
            setIsLoading(false);
        }
    };

    const createSiblingUnit = async (data: Outline) => {
        try {
            updateOutlineStatus(data.id, 'saving');
            setError(null);

            const parent = findNode(data.parentId || "");
            // get node index in children
            const index = parent.children.findIndex((child) => child.id === data.id);

            const newUnit = await api.createUnit({
                "parent_id": data.parent_id,
                "unit_index": index - 1,
                "chapter_id": data.parent_id,
                "unit_description": data.name,
                "unit_name": data.name,
                "shifu_id": currentShifu?.shifu_id
            });

            replaceOutline('new_chapter', {
                id: newUnit.id,
                name: newUnit.name,
                no: '',
                children: []
            })

        } catch (error) {
            console.error(error);
            setError("Failed to create chapter");
        } finally {
            setIsLoading(false);
        }
    }
    const updateOutlineStatus = (id: string, status: "new" | "edit" | "saving") => {
        setCataData({
            ...cataData,
            [id]: {
                ...cataData[id],
                status
            }
        })
    }
    const updateOuline = async (id: string, value: Outline) => {
        setCataData({
            ...cataData,
            [id]: {
                ...cataData[id],
                ...value
            }
        })
    }

    const addChapter = async (chapter: Outline) => {
        if (cataData['new_chapter']) {
            return;
        }
        if (chapters?.find((child: any) => child.id === 'new_chapter')) {
            return;
        }
        setChapters([...chapters, chapter]);
        updateOuline(chapter.id, {
            ...chapter,
            status: 'new'
        });
        setFocusId(chapter.id);
    }
    const replaceOutline = async (id: string, outline: Outline) => {
        const node = findNode(id)
        node.id = outline.id;
        node.name = outline.name;
        node.no = outline.no;
        node.parent_id = outline.parent_id;
        node.children = outline.children;
        setChapters([...chapters])
        delete cataData[id]
        setCataData({
            ...cataData,
            [outline.id]: {
                ...outline,
                status: 'edit'
            }
        })
    }

    const loadProfileItemDefinations = async (shifuId: string) => {
        const list = await api.getProfileItemDefinitions({
            parent_id: shifuId,
            type: "all"
        })
        setProfileItemDefinations(list);
    }
    const setBlockContentPropertiesById = (id: string, properties: AIBlockProperties | SolidContentBlockProperties, reset: boolean = false) => {
        if (reset) {
            setBlockContentProperties({
                ...blockContentProperties,
                [id]: properties
            });
            return;
        }
        setBlockContentProperties({
            ...blockContentProperties,
            [id]: {
                ...blockContentProperties[id],
                ...properties
            }
        })
    }
    const setBlockContentTypesById = (id: string, type: string) => {
        setBlockContentTypes({
            ...blockContentTypes,
            [id]: type
        })
    }
    const setBlockUIPropertiesById = (id: string, properties: any, reset: boolean = false) => {
        if (reset) {
            setBlockUIProperties({
                ...blockUIProperties,
                [id]: properties
            });
            return;
        }
        setBlockUIProperties({
            ...blockUIProperties,
            [id]: {
                ...blockUIProperties[id],
                ...properties
            }
        })
    }
    const setBlockUITypesById = (id: string, type: string) => {
        setBlockUITypes({
            ...blockUITypes,
            [id]: type
        })
    }
    const setBlockContentStateById = (id: string, state: 'edit' | 'preview') => {
        setBlockContentState({
            ...blockContentState,
            [id]: state
        })
    }
    const updateChapterOrder = async (chapter_ids: string[]) => {
        setIsSaving(true);
        setError(null);
        try {
            await api.updateChapterOrder({
                "chapter_ids": chapter_ids,
                "shifu_id": currentShifu?.shifu_id
            });
            setLastSaveTime(new Date());
        } catch (error) {
            console.error(error);
            setError("Failed to update chapter order");
        } finally {
            setIsSaving(false);
        }
    }
    const removeBlock = async (id: string) => {
        const list = blocks.filter((block) => block.properties.block_id !== id);
        setBlocks(list);
        autoSaveBlocks(currentNode!.id, list, blockContentTypes, blockContentProperties, blockUITypes, blockUIProperties, currentShifu?.shifu_id || '');
    }
    const loadModels = async () => {
        const list = await api.getModelList({});
        setModels(list);
    }

    const value: ShifuContextType = {
        currentShifu,
        chapters,
        isLoading,
        isSaving,
        error,
        lastSaveTime,
        focusId,
        focusValue,
        cataData,
        blocks,
        blockContentProperties,
        blockContentTypes,
        blockUIProperties,
        blockUITypes,
        blockContentState,
        currentNode,
        profileItemDefinations,
        models,
        actions: {
            setFocusId,
            addChapter,
            setChapters,
            loadShifu,
            loadChapters,
            createChapter,
            setFocusValue,
            updateOuline,
            addSubOutline,
            addSiblingOutline,
            removeOutline,
            replaceOutline,
            createSiblingUnit,
            createUnit,
            loadBlocks,
            addBlock,
            setBlockContentPropertiesById,
            setBlockContentTypesById,
            setBlockUIPropertiesById,
            setBlockUITypesById,
            updateChapterOrder,
            setBlockContentStateById,
            setBlocks,
            saveBlocks,
            autoSaveBlocks,
            saveCurrentBlocks,
            removeBlock,
            setCurrentNode,
            loadModels
        },
    };

    return <ShifuContext.Provider value={value}>{children}</ShifuContext.Provider>;
};

export const useShifu = (): ShifuContextType => {
    const context = useContext(ShifuContext);
    if (context === undefined) {
        throw new Error("useShifu must be used within a ShifuProvider");
    }
    return context;
};

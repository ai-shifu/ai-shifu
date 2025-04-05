import React, { createContext, useContext, useState, ReactNode, useCallback } from "react";
import { Scenario, ScenarioContextType, Outline, Block, ProfileItem } from "../types/scenario";
import api from "@/api";
import { ContentTypes } from "@/components/render-block";
import { UITypes } from "@/components/render-ui";
import { debounce } from "lodash";
const ScenarioContext = createContext<ScenarioContextType | undefined>(undefined);

const buildBlockList2 = (blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>) => {
    // build block list base on block content type,block content properties,block ui type,block ui properties
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

// const saveBlockToServer = debounce(async (outline: string, blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>) => {
//     const blockList = buildBlockList(blocks, blockContentTypes, blockContentProperties, blockUITypes, blockUIProperties);
//     await api.saveBlocks({ outline_id: outline, blocks: blockList });
// }, 3000);

export const ScenarioProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [currentScenario, setCurrentScenario] = useState<Scenario | null>(null);
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
    const [currentOutline, setCurrentOutline] = useState('');
    const [profileItemDefinations, setProfileItemDefinations] = useState<ProfileItem[]>([]);
    const loadScenario = async (scenarioId: string) => {
        console.log(scenarioId)
        // try {
        //     setIsLoading(true);
        //     setError(null);
        //     const scenario = await api.getScenario({ scenarioId });
        //     console.log(scenario)
        //     setCurrentScenario(scenario);
        // } catch (error) {
        //     console.error(error);
        //     setError("Failed to load scenario");
        // } finally {
        //     setIsLoading(false);
        // }
        // TODO
    };

    const recursiveCataData = (cataTree: Outline[]): any => {
        const result: any = {};
        const processItem = (item: any, parentId = "", depth = 0) => {
            result[item.id] = {
                ...cataData[item.id],
                parend_id: parentId,
                name: item.name,
                depth: depth, // 添加 depth 属性
                status: 'edit',
            };

            if (item.children) {
                item.children.forEach((child: any) => {
                    processItem(child, item.id, depth + 1); // 增加深度
                });
            }
        };

        cataTree.forEach((child: any) => {
            processItem(child, "", 0); // 初始深度为 0
        });
        return result;
    }
    const buildOutlineTree = (items: Outline[]) => {
        const treeData = recursiveCataData(items);
        setCataData(treeData);
        return treeData;
    }
    const findNode = (id: string) => {
        //递归遍历 chapters 查找id未某个值的节点
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
        if (outline.parentId) {
            const parent = findNode(outline.parentId || "");
            if (parent) {
                parent.children = parent.children?.filter((child: any) => child.id !== outline.id);
            }
            if (cataData[outline.id].status == 'edit') {
                if (outline.depth == 0) {
                    await api.deleteChapter({
                        chapter_id: outline.id
                    })
                } else if (outline.depth == 1) {
                    await api.deleteUnit({
                        unit_id: outline.id
                    })

                }
            }
            setChapters([...chapters])
        } else {
            const list = chapters.filter((child: any) => child.id !== outline.id);
            setChapters([...list])
            await api.deleteChapter({
                chapter_id: outline.id
            })
        }

    }

    const loadChapters = async (scenarioId: string) => {
        try {
            setIsLoading(true);
            setError(null);
            setCurrentScenario({
                id: scenarioId
            });
            const chaptersData = await api.getScenarioOutlineTree({ scenario_id: scenarioId });

            const list = chaptersData.map((chapter: any) => {
                return {
                    id: chapter.id,
                    name: chapter.name,
                    children: chapter.children,
                }
            })
            if (list.length > 0) {
                if (list[0].children && list[0].children.length > 0) {
                    setCurrentOutline(list[0].children[0].id);
                    loadBlocks(list[0].children[0].id);
                }
            }
            setChapters(list);
            buildOutlineTree(list);
            loadProfileItemDefinations(scenarioId);
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
        // build block list base on block content type,block content properties,block ui type,block ui properties
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
            // return {
            //     blockId: block.properties.block_id,
            //     blockType: blockContentTypes[block.properties.block_id],
            //     blockProperties: blockContentProperties[block.properties.block_id],
            //     blockUIType: blockUITypes[block.properties.block_id],
            //     blockUIProperties: blockUIProperties[block.properties.block_id]
            // }
        })
        return list;
    }

    const loadBlocks = async (outlineId: string) => {
        try {
            // setIsLoading(true);
            setError(null);
            setCurrentOutline(outlineId);
            // const id = '5071e9aa8d1246b5870c7970b679b7d4';
            const blocksData = await api.getBlocks({ outline_id: outlineId });
            const list = blocksData.filter(p => p.type == 'block') as Block[];
            setBlocks(list);
            initBlockContentTypes(list);
            initBlockContentProperties(list);
            const blockUIList = list.filter(p => p.properties.block_ui);
            initBlockUITypes(blockUIList);
            initBlockUIProperties(blockUIList);


        } catch (error) {
            console.error(error);
            setError("Failed to load blocks");
        }
    }
    const saveBlocks = async () => {
        const list = buildBlockList(blocks);
        try {
            // setIsLoading(true);
            setError(null);
            // const id = '5071e9aa8d1246b5870c7970b679b7d4';
            await api.saveBlocks({ outline_id: currentOutline, blocks: list });
            // setBlocks(list);
        } catch (error) {
            console.error(error);
            setError("Failed to save blocks");
        }
    }
    const addBlock = async (index: number, blockType: string = 'ai') => {
        const item = ContentTypes.find(p => p.type == blockType);
        const buttonUI = UITypes[0];
        // const block = {
        //     "properties": {
        //         block_id: uuidv4(),
        //         "block_no": "",
        //         "block_name": "",
        //         "block_desc": "",
        //         "block_type": 101,
        //         "block_index": index,
        //         "block_content": {
        //             type: blockType,
        //             properties: item?.properties
        //         },
        //         "block_ui": buttonUI
        //     },
        //     "type": "block"
        // }
        const block = await api.addBlock({
            "block": {
                "block_content": {
                    type: blockType,
                    properties: item?.properties
                },
                "block_desc": "",
                // "block_id": "",
                "block_index": index,
                "block_name": "",
                "block_no": "",
                "block_type": 0,
                "block_ui": buttonUI
            },
            "block_index": index,
            "outline_id": currentOutline
        })

        blocks.splice(index, 0, block);
        console.log(blocks)
        const list = [...blocks];
        console.log(list)
        setBlockContentTypes({
            ...blockContentTypes,
            [block.properties.block_id]: blockType
        })
        setBlockContentProperties({
            ...blockContentProperties,
            [block.properties.block_id]: item?.properties
        })
        // initBlockContentTypes(list);
        // initBlockContentProperties(list);

        // const blockUIList = list.filter(p => p.properties.block_ui);
        // initBlockUITypes(blockUIList);
        // initBlockUIProperties(blockUIList);
        setBlockUITypes({
            ...blockUITypes,
            [block.properties.block_id]: buttonUI.type
        })
        setBlockUIProperties({
            ...blockUIProperties,
            [block.properties.block_id]: buttonUI.properties
        })
        setBlockContentStateById(block.properties.block_id, 'edit');
        setBlocks(list);
    }
    const addSubOutline = async (parent: Outline, name = '') => {
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
    // const autoSaveBlocks2 = async (outlineId: string, blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>) => {
    //     try {
    //         setIsSaving(true);
    //         setError(null);
    //         setIsSaving(true);
    //         setError(null);

    //         await saveBlockToServer(outlineId, blocks, blockContentTypes, blockContentProperties, blockUITypes, blockUIProperties);
    //         setIsSaving(false);
    //         setLastSaveTime(new Date());
    //     } catch (error) {
    //         console.error(error);
    //         setError("Failed to save chapter");
    //     } finally {
    //         setIsSaving(false);
    //     }
    // }
    const autoSaveBlocks = useCallback(debounce(async (outline: string, blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>) => {

        setIsSaving(true);
        setError(null);
        setIsSaving(true);
        try {
            setError(null);
            const blockList = buildBlockList2(blocks, blockContentTypes, blockContentProperties, blockUITypes, blockUIProperties);
            await api.saveBlocks({ outline_id: outline, blocks: blockList });
            setIsSaving(false);
            setLastSaveTime(new Date());
        } catch (error: any) {
            console.error(error);
            setError(error.message);
        } finally {
            setIsSaving(false);
            setLastSaveTime(new Date());
        }
    }, 3000), []) as (outline: string, blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>) => Promise<void>


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
        try {
            updateOutlineStatus(data.id, 'saving');
            setError(null);
            const index = chapters.findIndex((child) => child.id === data.id);

            if (data.id === 'new_chapter') {
                const newChapter = await api.createChapter({
                    parent_id: data.parent_id,
                    "chapter_description": data.name,
                    "chapter_index": index,
                    "chapter_name": data.name,
                    "scenario_id": currentScenario?.id
                });
                replaceOutline('new_chapter', {
                    id: newChapter.chapter_id,
                    name: newChapter.chapter_name,
                    no: '',
                    children: []
                })
            } else {
                await api.modifyChapter({
                    "chapter_id": data.id,
                    "chapter_index": index,
                    "chapter_description": data.name,
                    "chapter_name": data.name
                })
                replaceOutline(data.id, {
                    id: data.id,
                    name: data.name,
                    no: '',
                    children: []
                })
            }


        } catch (error) {
            console.error(error);
            setError("Failed to create chapter");
        } finally {
            setIsLoading(false);
        }
    };

    const createUnit = async (data: Outline) => {
        try {
            console.log('createUnit')
            updateOutlineStatus(data.id, 'saving');
            setError(null);

            const parent = findNode(data.parent_id || "");
            // get node index in children
            const index = parent.children.findIndex((child) => child.id === data.id);

            if (data.id === 'new_chapter') {
                const newUnit = await api.createUnit({
                    parent_id: data.parent_id,
                    "unit_index": index,
                    "chapter_id": data.parent_id,
                    "unit_description": data.name,
                    "unit_name": data.name,
                    "scenario_id": currentScenario?.id
                });

                replaceOutline('new_chapter', {
                    id: newUnit.id,
                    name: newUnit.name,
                    no: '',
                    children: []
                })
            } else {
                await api.modifyUnit({
                    "unit_id": data.id,
                    "unit_index": index,
                    "unit_description": data.name,
                    "unit_name": data.name,
                })
                replaceOutline(data.id, {
                    id: data.id,
                    name: data.name,
                    no: '',
                    children: []
                })
            }

        } catch (error) {
            console.error(error);
            setError("Failed to create chapter");
        } finally {
            setIsLoading(false);
        }
    };

    const createSiblingUnit = async (data: Outline) => {
        try {
            console.log('createSiblingUnit')
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
                "scenario_id": currentScenario?.id
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
        console.log(id, value)
        setCataData({
            ...cataData,
            [id]: {
                ...cataData[id],
                ...value
            }
        })
    }

    const addChapter = async (chapter: Outline) => {
        console.log(chapter)
        setChapters([...chapters, chapter]);
        updateOuline(chapter.id, {
            ...chapter,
            status: 'new'
        })
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
        // console.log(chapters)
        delete cataData[id]
        setCataData({
            ...cataData,
            [outline.id]: {
                ...outline,
                status: 'edit'
            }
        })
    }

    const loadProfileItemDefinations = async (scenarioId: string) => {
        const list = await api.getProfileItemDefinations({
            parent_id: scenarioId,
            type: "all"
        })
        setProfileItemDefinations(list);
    }
    const setBlockContentPropertiesById = (id: string, properties: any) => {
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
    const setBlockUIPropertiesById = (id: string, properties: any) => {
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
        await api.updateChapterOrder({
            "chapter_ids": chapter_ids,
            "scenario_id": currentScenario?.id
        })
    }
    const removeBlock = async (id: string) => {
        const list = blocks.filter((block) => block.properties.block_id !== id);
        setBlocks(list);
        autoSaveBlocks(currentOutline, list, blockContentTypes, blockContentProperties, blockUITypes, blockUIProperties);
    }
    // console.log(blockUIProperties)
    const value: ScenarioContextType = {
        currentScenario,
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
        currentOutline,
        profileItemDefinations,
        actions: {
            setFocusId,
            addChapter,
            setChapters,
            loadScenario,
            loadChapters,
            // saveChapter,
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
            saveBlocks,
            autoSaveBlocks,
            removeBlock
        },
    };
    // const init = async () => {
    //     // await loadScenario(id);
    //     await loadChapters(id);
    // }
    // useEffect(() => {
    //     init();
    // }, [])

    return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>;
};

export const useScenario = (): ScenarioContextType => {
    const context = useContext(ScenarioContext);
    if (context === undefined) {
        throw new Error("useScenario must be used within a ScenarioProvider");
    }
    return context;
};

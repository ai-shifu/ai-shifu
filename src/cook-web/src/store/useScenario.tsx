import React, { createContext, useContext, useState, ReactNode, useCallback, useRef } from "react";
import { Scenario, ScenarioContextType, Outline, Block } from "../types/scenario";
import api from "@/api";
import { v4 as uuidv4 } from 'uuid';

const ScenarioContext = createContext<ScenarioContextType | undefined>(undefined);

export const ScenarioProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [currentScenario, setCurrentScenario] = useState<Scenario | null>(null);
    const [chapters, setChapters] = useState<Outline[]>([]);
    const [currentChapter, setCurrentChapter] = useState<Outline | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lastSaveTime, setLastSaveTime] = useState<Date | null>(null);
    const saveTimeoutRef = useRef<NodeJS.Timeout>(null);
    const [focusId, setFocusId] = useState('');
    const [focusValue, setFocusValue] = useState('');
    const [cataData, setCataData] = useState<{ [x: string]: Outline }>({})
    const [blocks, setBlocks] = useState<Block[]>([]);
    const [blockContentProperties, setBlockContentProperties] = useState<{ [x: string]: any }>({});
    const [blockContentTypes, setBlockContentTypes] = useState<{ [x: string]: string }>({});
    const [blockUIProperties, setBlockUIProperties] = useState<{ [x: string]: any }>({});
    const [blockUITypes, setBlockUITypes] = useState<{ [x: string]: string }>({});

    const loadScenario = async (scenarioId: string) => {
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
        setCataData(treeData)
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
            buildOutlineTree(list);
            setChapters(list);
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
    const loadBlocks = async (outlineId: string) => {
        try {
            // setIsLoading(true);
            setError(null);
            const blocksData = await api.getBlocks({ outline_id: '5071e9aa8d1246b5870c7970b679b7d4' });
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
    const saveChapter = useCallback(async (chapter: Outline) => {
        // Clear any existing timeout
        if (saveTimeoutRef.current) {
            clearTimeout(saveTimeoutRef.current);
        }

        // Set a new timeout
        saveTimeoutRef.current = setTimeout(async () => {
            try {
                setIsSaving(true);
                setError(null);
                await api.modifyChapter(chapter);
                setChapters(chapters.map(ch =>
                    ch.id === chapter.id ? chapter : ch
                ));
                if (currentChapter?.id === chapter.id) {
                    setCurrentChapter(chapter);
                }
                setLastSaveTime(new Date());
            } catch (error) {
                console.error(error);
                setError("Failed to save chapter");
            } finally {
                setIsSaving(false);
            }
        }, 3000); // 3 seconds delay
    }, [chapters, currentChapter]);

    const createChapter = async (chapterData: Outline) => {
        try {
            updateOutlineStatus(chapterData.id, 'saving');
            setError(null);
            const newChapter = await api.createChapter({
                parent_id: chapterData.parent_id,
                "chapter_description": chapterData.name,
                "chapter_index": 0,
                "chapter_name": chapterData.name,
                "scenario_id": currentScenario?.id
            });
            replaceOutline('new_chapter', {
                id: newChapter.chapter_id,
                name: newChapter.chapter_name,
                no: '',
                children: []
            })

        } catch (error) {
            console.error(error);
            setError("Failed to create chapter");
        } finally {
            setIsLoading(false);
        }
    };

    const createUnit = async (data: Outline) => {
        try {
            updateOutlineStatus(data.id, 'saving');
            setError(null);

            const newUnit = await api.createUnit({
                parent_id: data.parent_id,
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
    console.log(blockContentProperties)
    // console.log(blockUIProperties)
    const value: ScenarioContextType = {
        currentScenario,
        chapters,
        currentChapter,
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
        actions: {
            setFocusId,
            addChapter,
            setChapters,
            loadScenario,
            loadChapters,
            setCurrentChapter,
            saveChapter,
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
            setBlockContentPropertiesById,
            setBlockContentTypesById,
            setBlockUIPropertiesById,
            setBlockUITypesById,
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

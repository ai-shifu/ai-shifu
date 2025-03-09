import React, { createContext, useContext, useState, ReactNode, useCallback, useRef } from "react";
import { Scenario, ScenarioContextType, Outline } from "../types/scenario";
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
        console.log(result);
        return result;
    }
    const buildOutlineTree = (items: Outline[]) => {
        const treeData = recursiveCataData(items);
        console.log(treeData)
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
                    const result = find(nodes[i].children);
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
        const parent = findNode(outline.parent_id || "");
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
    }

    const loadChapters = async (scenarioId: string) => {
        try {
            setIsLoading(true);
            setError(null);
            setCurrentScenario({
                scenario_id: scenarioId
            });
            const chaptersData = await api.getScenarioOutlineTree({ scenario_id: scenarioId });
            console.log(chaptersData)

            const list = chaptersData.map((chapter) => {
                return {
                    id: chapter.outline_id,
                    name: chapter.outline_name,
                    children: chapter.outline_children,
                }
            })
            console.log(list)
            buildOutlineTree(list);
            setChapters(list);
        } catch (error) {
            console.error(error);
            setError("Failed to load chapters");
        } finally {
            setIsLoading(false);
        }
    };
    const addSubOutline = async (parent: Outline, name = '') => {
        const id = uuidv4();
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
                "chapter_id": chapterData.id,
                "chapter_description": chapterData.name,
                "chapter_index": 0,
                "chapter_name": chapterData.name,
                "scenario_id": currentScenario?.scenario_id
            });

            // setChapters([...chapters, {
            //     id: newChapter.chapter_id,
            //     name: newChapter.chapter_name,
            //     no: newChapter.chapter_type,
            //     children: []
            // }]);

            updateOutlineStatus(chapterData.id, 'edit');

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
            const newChapter = await api.createUnit({
                parent_id: data.parent_id,
                "chapter_id": data.id,
                "unit_description": data.name,
                "unit_name": data.name,
                "scenario_id": currentScenario?.scenario_id
            });

            // setChapters([...chapters, {
            //     id: newChapter.chapter_id,
            //     name: newChapter.chapter_name,
            //     no: newChapter.chapter_type,
            //     children: []
            // }]);
            updateOutlineStatus(data.id, 'edit');

        } catch (error) {
            console.error(error);
            setError("Failed to create chapter");
        } finally {
            setIsLoading(false);
        }
    };
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
        setChapters([...chapters, chapter]);
        updateOuline(chapter.id, {
            ...chapter,
            status: 'new'
        })
        setFocusId(chapter.id);
    }
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
            removeOutline,
            createUnit
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

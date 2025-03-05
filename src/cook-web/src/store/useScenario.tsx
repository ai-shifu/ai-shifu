import React, { createContext, useContext, useState, ReactNode, useCallback, useRef } from "react";
import { Scenario, Chapter, ScenarioContextType } from "../types/scenario";
import api from "@/api";

const ScenarioContext = createContext<ScenarioContextType | undefined>(undefined);

export const ScenarioProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [currentScenario, setCurrentScenario] = useState<Scenario | null>(null);
    const [chapters, setChapters] = useState<Chapter[]>([]);
    const [currentChapter, setCurrentChapter] = useState<Chapter | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lastSaveTime, setLastSaveTime] = useState<Date | null>(null);
    const saveTimeoutRef = useRef<NodeJS.Timeout>(null);

    const loadScenario = async (scenarioId: string) => {
        try {
            setIsLoading(true);
            setError(null);
            const scenario = await api.getScenario({ scenarioId });
            setCurrentScenario(scenario);
        } catch (error) {
            console.error(error);
            setError("Failed to load scenario");
        } finally {
            setIsLoading(false);
        }
    };

    const loadChapters = async (scenarioId: string) => {
        try {
            setIsLoading(true);
            setError(null);
            const chaptersData = await api.getScenarioChapters({ scenario_id: scenarioId });
            console.log(chaptersData)
            setChapters(chaptersData);
        } catch (error) {
            console.error(error);
            setError("Failed to load chapters");
        } finally {
            setIsLoading(false);
        }
    };

    const saveChapter = useCallback(async (chapter: Chapter) => {
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
                    ch.chapter_id === chapter.chapter_id ? chapter : ch
                ));
                if (currentChapter?.chapter_id === chapter.chapter_id) {
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

    const createChapter = async (chapterData: Omit<Chapter, "chapter_id">) => {
        try {
            setIsLoading(true);
            setError(null);
            const newChapter = await api.createChapter(chapterData);
            setChapters([...chapters, newChapter]);
        } catch (error) {
            console.error(error);
            setError("Failed to create chapter");
        } finally {
            setIsLoading(false);
        }
    };

    const value: ScenarioContextType = {
        currentScenario,
        chapters,
        currentChapter,
        isLoading,
        isSaving,
        error,
        lastSaveTime,
        actions: {
            setChapters,
            loadScenario,
            loadChapters,
            setCurrentChapter,
            saveChapter,
            createChapter,
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

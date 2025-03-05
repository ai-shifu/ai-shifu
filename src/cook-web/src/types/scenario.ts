// export interface Scenario {
//     scenario_id: string;
//     scenario_name: string;
//     scenario_description: string;
//     is_favorite: boolean;
//     created_at: string;
//     updated_at: string;
// }


// interface Scenario {
//   scenario_description: string;
//   scenario_image: string;
//   scenario_name: string;
// }


export interface Scenario {
    scenario_id: string;
    scenario_name: string;
    scenario_description: string;
    scenario_image: string;
    scenario_state: number;
    is_favorite: boolean;
}

export interface Chapter {
    chapter_description: string;
    chapter_index?: number;
    chapter_name: string;
    chapter_id: string;
    scenario_id: string;
}

export interface ScenarioState {
    currentScenario: Scenario | null;
    chapters: Chapter[];
    currentChapter: Chapter | null;
    isLoading: boolean;
    isSaving: boolean;
    error: string | null;
    lastSaveTime: Date | null;
}

export interface ScenarioActions {
    loadScenario: (scenarioId: string) => Promise<void>;
    loadChapters: (scenarioId: string) => Promise<void>;
    setCurrentChapter: (chapter: Chapter) => void;
    saveChapter: (chapter: Chapter) => Promise<void>;
    createChapter: (chapter: Omit<Chapter, 'chapter_id'>) => Promise<void>;
    setChapters: (chapters: Chapter[]) => void;
}

export interface ScenarioContextType extends ScenarioState {
    actions: ScenarioActions;
}

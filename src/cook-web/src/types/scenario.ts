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
    id: string;
    name?: string;
    description?: string;
    image?: string;
    state?: number;
    is_favorite?: boolean;
}

// export interface Outline {
//     chapter_description: string;
//     chapter_index?: number;
//     chapter_name: string;
//     chapter_id: string;
//     scenario_id: string;
// }

export interface Outline {
    parent_id?: string;
    parentId?: string;
    id: string;
    no?: string;
    name?: string;
    children?: Outline[];
    depth?: number;
    status?: 'new' | 'edit' | 'saving';
}

export interface ScenarioState {
    currentScenario: Scenario | null;
    chapters: Outline[];
    currentChapter: Outline | null;
    isLoading: boolean;
    isSaving: boolean;
    error: string | null;
    lastSaveTime: Date | null;
    focusId: string | null;
    focusValue: string | null;
    cataData: { [x: string]: Outline };
}

export interface ScenarioActions {
    addChapter: (chapter: Outline) => void;
    loadScenario: (scenarioId: string) => Promise<void>;
    loadChapters: (scenarioId: string) => Promise<void>;
    setCurrentChapter: (chapter: Outline) => void;
    saveChapter: (chapter: Outline) => Promise<void>;
    createChapter: (chapter: Omit<Outline, 'chapter_id'>) => Promise<void>;
    setChapters: (chapters: Outline[]) => void;
    setFocusId: (id: string) => void;
    setFocusValue: (value: string) => void;
    updateOuline: (id: string, chapter: Outline) => Promise<void>;
    addSubOutline: (parent: Outline, name: string) => Promise<void>;
    addSiblingOutline: (item: Outline, name: string) => Promise<void>;
    removeOutline: (item: Outline) => Promise<void>;
    replaceOutline: (id: string, outline: Outline) => Promise<void>;
    createUnit: (chapter: Outline) => Promise<void>;
    createSiblingUnit: (chapter: Outline) => Promise<void>;
}

export interface ScenarioContextType extends ScenarioState {
    actions: ScenarioActions;
}

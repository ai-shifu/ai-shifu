
export type BlockType = 'ai' | 'systemprompt' | 'solidcontent';

export interface Scenario {
    id: string;
    name?: string;
    description?: string;
    image?: string;
    state?: number;
    is_favorite?: boolean;
}

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

export interface Block {
    properties: {
        block_content: any;
        block_desc: string;
        block_id: string;
        block_index: number;
        block_name: string;
        block_no: string;
        block_type: number;
        block_ui: any;
    }
    type: string;
}

export interface ColorSetting {
    color: string;
    text_color: string;
}

export interface ProfileItem {
    profile_key: string;
    color_setting: ColorSetting;
    profile_type: string;
}


export interface ScenarioState {
    currentScenario: Scenario | null;
    chapters: Outline[];
    isLoading: boolean;
    isSaving: boolean;
    lastSaveTime: Date | null;
    error: string | null;
    focusId: string | null;
    focusValue: string | null;
    cataData: { [x: string]: Outline };
    blocks: Block[];
    blockUIProperties: { [x: string]: any };
    blockUITypes: { [x: string]: string };
    blockContentProperties: { [x: string]: any };
    blockContentTypes: { [x: string]: string };
    blockContentState: { [x: string]: 'edit' | 'preview' };
    profileItemDefinations: ProfileItem[];
    currentNode: Outline | null;
    models: string[];
}

export interface ScenarioActions {
    addChapter: (chapter: Outline) => void;
    loadScenario: (scenarioId: string) => Promise<void>;
    loadChapters: (scenarioId: string) => Promise<void>;
    // saveChapter: (chapter: Outline) => Promise<void>;
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
    loadBlocks: (outlineId: string, scenario_id: string) => void;
    addBlock: (index: number, type: BlockType, scenario_id: string) => void;
    setBlockContentPropertiesById: (id: string, properties: AIBlockProperties | SolidContentBlockProperties, reset?: boolean) => void;
    setBlockContentTypesById: (id: string, type: string) => void;
    setBlockUIPropertiesById: (id: string, properties: any, reset?: boolean) => void;
    setBlockUITypesById: (id: string, type: string) => void;
    updateChapterOrder: (chapterIds: string[]) => Promise<void>
    setBlockContentStateById: (id: string, state: 'edit' | 'preview') => void;
    setBlocks: (blocks: Block[]) => void;
    saveBlocks: (scenario_id: string) => Promise<void>;
    autoSaveBlocks: (outline: string, blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>, scenario_id: string) => Promise<void>;
    saveCurrentBlocks: (outline: string, blocks: Block[], blockContentTypes: Record<string, any>, blockContentProperties: Record<string, any>, blockUITypes: Record<string, any>, blockUIProperties: Record<string, any>, scenario_id: string) => Promise<void>;
    removeBlock: (id: string, scenario_id: string) => Promise<void>;
    setCurrentNode: (node: Outline) => void;
    loadModels: () => void;
}

export interface ScenarioContextType extends ScenarioState {
    actions: ScenarioActions;
}


export interface AIBlockProperties {
    prompt: string,
    profiles?: string[],
    model?: string,
    temprature?: string,
    other_conf?: string
}

export interface SolidContentBlockProperties {
    content: string,
    profiles?: string[]
}

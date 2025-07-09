export type BlockType = | 'content' | 'button' | 'login' | 'payment' | 'options' | 'goto' | 'input';

export interface Shifu {
    bid: string;
    name?: string;
    description?: string;
    avatar?: string;
    state?: number;
    is_favorite?: boolean;
}

export interface Outline {
    id: string;
    bid: string;
    parent_bid?: string;
    parentId?: string;
    position?: string;
    name?: string;
    children?: Outline[];
    depth?: number;
    status?: 'new' | 'edit' | 'saving';
    shifu_bid?: string;
}

export interface Block {
    bid: string;
    properties: any;
    type: string;
    variable_bids: string[];
    resource_bids: string[];
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

export interface ProfileItemDefination {
    profile_id: string;
    profile_key: string;
    value: string;
}

export interface ShifuState {
    currentShifu: Shifu | null;
    chapters: Outline[];
    isLoading: boolean;
    isSaving: boolean;
    lastSaveTime: Date | null;
    error: string | null;
    focusId: string | null;
    focusValue: string | null;
    cataData: { [x: string]: Outline };
    blockTypes: { [x: string]: BlockType };
    blocks: Block[];
    // blockUIProperties: { [x: string]: any };
    blockUITypes: { [x: string]: string };
    blockContentProperties: { [x: string]: any };
    blockContentTypes: { [x: string]: string };
    blockContentState: { [x: string]: 'edit' | 'preview' };
    blockProperties: { [x: string]: any };
    blockErrors: { [x: string]: string | null };
    profileItemDefinations: ProfileItem[];
    currentNode: Outline | null;
    models: string[];
}

export interface ApiResponse<T> {
    code: number;
    message: string;
    data: T;
}

export interface SaveBlockListResult {
    blocks: Block[];
    error_messages: Record<string, string>;
}

export interface ReorderOutlineItemDto {
    bid: string;
    children: ReorderOutlineItemDto[];
}

export interface ShifuActions {
    addChapter: (chapter: Outline) => void;
    loadShifu: (shifuId: string) => Promise<void>;
    loadChapters: (shifuId: string) => Promise<void>;
    createChapter: (chapter: Omit<Outline, 'chapter_id'>) => Promise<void>;
    setChapters: (chapters: Outline[]) => void;
    setFocusId: (id: string) => void;
    setFocusValue: (value: string) => void;
    updateOuline: (id: string, chapter: Outline) => Promise<void>;
    addSubOutline: (parent: Outline, name: string) => Promise<void>;
    addSiblingOutline: (item: Outline, name: string) => Promise<void>;
    removeOutline: (item: Outline) => Promise<void>;
    replaceOutline: (id: string, outline: Outline) => Promise<void>;
    createOutline: (outline: Outline) => Promise<void>;
    createSiblingUnit: (chapter: Outline) => Promise<void>;
    loadBlocks: (outlineId: string, shifuId: string) => void;
    addBlock: (index: number, type: BlockType, shifuId: string) => Promise<string>;
    setBlockContentPropertiesById: (id: string, properties: AIBlockProperties | SolidContentBlockProperties, reset?: boolean) => void;
    setBlockContentTypesById: (id: string, type: BlockType) => void;
    setBlockUIPropertiesById: (id: string, properties: any, reset?: boolean) => void;
    setBlockUITypesById: (id: string, type: BlockType) => void;
    updateChapterOrder: (move_chapter_id: string, move_to_parent_id?: string, chapterIds?: string[]) => Promise<void>
    setBlockContentStateById: (id: string, state: 'edit' | 'preview') => void;
    setBlocks: (blocks: Block[]) => void;
    saveBlocks: (shifuId: string) => Promise<void>;
    autoSaveBlocks: (outline: string, blocks: Block[], blockTypes: Record<string, any>, blockProperties: Record<string, any>, shifuId: string) => Promise<ApiResponse<SaveBlockListResult> | null>;
    saveCurrentBlocks: (outline: string, blocks: Block[], blockTypes: Record<string, any>, blockProperties: Record<string, any>, shifuId: string) => Promise<ApiResponse<SaveBlockListResult> | null>;
    removeBlock: (id: string, shifuId: string) => Promise<void>;
    setCurrentNode: (node: Outline) => void;
    loadModels: () => void;
    setBlockError: (blockId: string, error: string | null) => void;
    clearBlockErrors: () => void;
    reorderOutlineTree: (outlines: ReorderOutlineItemDto[]) => Promise<void>;
    updateBlockProperties: (bid: string, properties: any) => Promise<void>;
}

export interface ShifuContextType extends ShifuState {
    actions: ShifuActions;
}

export interface AIBlockProperties {
    prompt: string,
    profiles?: string[],
    model?: string,
    temperature?: string,
    other_conf?: string
}

export interface SolidContentBlockProperties {
    content: string,
    profiles?: string[]
}


export interface LabelDTO {
    lang: Record<string, string>;
}

export interface ContentDTO {
    content: string;
    llm_enabled: boolean;
    llm: string;
    llm_temperature: number;
}

export interface ButtonDTO {
    label: LabelDTO;
}

export interface InputDTO {
    placeholder: LabelDTO;
    prompt: string;
    result_variable_bids: string[];
    llm: string;
    llm_temperature: number;
}

export interface OptionItemDTO {
    label: LabelDTO;
    value: string;
}

export interface OptionsDTO {
    result_variable_bid: string;
    options: OptionItemDTO[];
}

export interface GotoConditionDTO {
    destination_type: string;
    destination_bid: string;
    value: string;
}

export interface GotoDTO {
    conditions: GotoConditionDTO[];
}

export interface BlockDTO {
    bid: string;
    type: string;
    properties: ContentDTO | ButtonDTO | InputDTO | OptionsDTO | GotoDTO;
    variable_bids: string[];
    resource_bids: string[];
}

export interface UIBlockDTO {
    data: BlockDTO;
    id: string;
    onPropertiesChange: (properties: BlockDTO) => void;
    onChanged: (changed: boolean) => void;
    onEditChange: (isEdit: boolean) => void;
    isEdit: boolean;
    isChanged: boolean;
}

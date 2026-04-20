import type { PreviewVariablesMap } from '@/components/lesson-preview/variableStorage';
import type { LearningPermission } from '@/c-api/studyV2';

export type BlockType =
  | 'content'
  | 'button'
  | 'login'
  | 'payment'
  | 'options'
  | 'goto'
  | 'input';

export interface ModelOption {
  value: string;
  label: string;
}

export interface Shifu {
  bid: string;
  name?: string;
  description?: string;
  avatar?: string;
  state?: number;
  is_favorite?: boolean;
  readonly?: boolean;
  archived?: boolean;
  created_user_bid?: string;
  can_manage_archive?: boolean;
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
  is_hidden?: boolean;
  type?: LearningPermission;
  system_prompt?: string;
  collapsed?: boolean;
}

export interface LessonCreationSettings {
  name: string;
  learningPermission: LearningPermission;
  isHidden: boolean;
  systemPrompt: string;
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
  profile_id?: string;
  profile_key: string;
  color_setting: ColorSetting;
  profile_type: string;
  profile_scope?: string;
  profile_scope_str?: string;
  profile_remark?: string;
  is_hidden?: boolean;
}

export interface ProfileItemDefinition {
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
  models: ModelOption[];
  mdflow: string;
  variables: string[];
  hiddenVariables: string[];
  systemVariables: Record<string, string>[];
  unusedVariables: string[];
  hideUnusedMode: boolean;
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

// Snapshot payload for mdflow saving to avoid relying on mutable state
export interface SaveMdflowPayload {
  shifu_bid?: string;
  outline_bid?: string;
  data?: string;
}

export interface ShifuActions {
  addChapter: (chapter: Outline) => void;
  addRootOutline: (settings: LessonCreationSettings) => Promise<void>;
  loadShifu: (shifuId: string, options?: { silent?: boolean }) => Promise<void>;
  loadChapters: (shifuId: string) => Promise<void>;
  createChapter: (chapter: Omit<Outline, 'chapter_id'>) => Promise<void>;
  setChapters: (chapters: Outline[]) => void;
  setFocusId: (id: string) => void;
  setFocusValue: (value: string) => void;
  updateOutline: (id: string, chapter: Outline) => Promise<void>;
  addSubOutline: (
    parent: Outline,
    settings: LessonCreationSettings,
  ) => Promise<void>;
  addSiblingOutline: (
    item: Outline,
    settings: LessonCreationSettings,
  ) => Promise<void>;
  removeOutline: (item: Outline) => Promise<void>;
  replaceOutline: (id: string, outline: Outline) => Promise<void>;
  createOutline: (outline: Outline) => Promise<void>;
  createSiblingUnit: (chapter: Outline) => Promise<void>;
  loadBlocks: (outlineId: string, shifuId: string) => void;
  setBlockContentPropertiesById: (
    id: string,
    properties: AIBlockProperties | SolidContentBlockProperties,
    reset?: boolean,
  ) => void;
  setBlockContentTypesById: (id: string, type: BlockType) => void;
  setBlockUIPropertiesById: (
    id: string,
    properties: any,
    reset?: boolean,
  ) => void;
  setBlockUITypesById: (id: string, type: BlockType) => void;
  updateChapterOrder: (
    move_chapter_id: string,
    move_to_parent_id?: string,
    chapterIds?: string[],
  ) => Promise<void>;
  setBlockContentStateById: (id: string, state: 'edit' | 'preview') => void;
  setBlocks: (blocks: Block[]) => void;
  saveBlocks: (shifuId: string) => Promise<void>;
  autoSaveBlocks: (
    payload?: SaveMdflowPayload,
  ) => Promise<ApiResponse<SaveBlockListResult> | null>;
  flushAutoSaveBlocks: (payload?: SaveMdflowPayload) => void;
  cancelAutoSaveBlocks: () => void;
  saveCurrentBlocks: (
    outline: string,
    blocks: Block[],
    blockTypes: Record<string, any>,
    blockProperties: Record<string, any>,
    shifuId: string,
  ) => Promise<ApiResponse<SaveBlockListResult> | null>;
  removeBlock: (id: string, shifuId: string) => Promise<void>;
  setCurrentNode: (node: Outline) => void;
  loadModels: () => Promise<void>;
  setBlockError: (blockId: string, error: string | null) => void;
  clearBlockErrors: () => void;
  reorderOutlineTree: (outlines: ReorderOutlineItemDto[]) => Promise<void>;
  updateBlockProperties: (bid: string, properties: any) => Promise<void>;
  loadMdflow: (outlineId: string, shifuId: string) => Promise<void>;
  saveMdflow: (payload?: SaveMdflowPayload) => Promise<void>;
  setCurrentMdflow: (value: string) => void;
  getCurrentMdflow: () => string;
  hasUnsavedMdflow: (outlineId?: string, value?: string) => boolean;
  parseMdflow: (
    value: string,
    shifuId: string,
    outlineId: string,
  ) => Promise<void>;
  previewParse: (
    value: string,
    shifuId: string,
    outlineId: string,
  ) => Promise<{
    variables: PreviewVariablesMap;
    blocksCount: number;
    systemVariableKeys: string[];
    allVariableKeys?: string[];
    unusedKeys?: string[];
  }>;
  hideUnusedVariables: (shifuId: string) => Promise<void>;
  restoreHiddenVariables: (shifuId: string) => Promise<void>;
  hideVariableByKey: (shifuId: string, key: string) => Promise<void>;
  unhideVariablesByKeys: (shifuId: string, keys: string[]) => Promise<void>;
  refreshProfileDefinitions: (
    shifuId: string,
    options?: { forceRefresh?: boolean },
  ) => Promise<{
    list: ProfileItem[];
    systemVariableKeys: string[];
    unusedKeys?: string[];
  }>;
  refreshVariableUsage: (shifuId: string) => Promise<{
    used_keys?: string[];
    unused_keys?: string[];
  } | null>;
  syncHiddenVariablesToUsage: (
    shifuId: string,
    options?: { unusedKeys?: string[]; hiddenKeys?: string[] },
  ) => Promise<void>;
  insertPlaceholderChapter: () => void;
  insertPlaceholderLesson: (parent: Outline) => void;
  removePlaceholderOutline: (outline: Outline) => void;
}

export interface ShifuContextType extends ShifuState {
  actions: ShifuActions;
}

export interface AIBlockProperties {
  prompt: string;
  profiles?: string[];
  model?: string;
  temperature?: string;
  other_conf?: string;
}

export interface SolidContentBlockProperties {
  content: string;
  profiles?: string[];
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

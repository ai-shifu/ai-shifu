export type DebugVariableValues = Record<string, string>;
export type DebugCourseAliases = Record<string, string>;
export type DebugCourseAliasPatch = Record<string, string | null>;

export interface StoredDebugVariableValues {
  system: DebugVariableValues;
  course: DebugVariableValues;
}

export interface DebugSessionPreparation {
  variableValues: DebugVariableValues;
  blockCount: number;
  systemVariableKeys: string[];
  allVariableKeys?: string[];
  unusedVariableKeys?: string[];
}

export interface DebugRunParams {
  shifuBid?: string;
  outlineBid?: string;
  mdflow?: string;
  userInput?: Record<string, unknown>;
  variableValues?: Record<string, unknown>;
  courseAliases?: DebugCourseAliases;
  blockIndex?: number;
  maxBlockCount?: number;
  reloadGeneratedBlockBid?: string;
  reloadElementBid?: string;
  systemVariableKeys?: string[];
}

export type DebugVariableValues = Record<string, string>;

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
  blockIndex?: number;
  maxBlockCount?: number;
  reloadGeneratedBlockBid?: string;
  reloadElementBid?: string;
  systemVariableKeys?: string[];
}

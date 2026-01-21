'use client';

import {
  Shifu,
  ShifuContextType,
  Outline,
  Block,
  ProfileItem,
  AIBlockProperties,
  SolidContentBlockProperties,
  SaveBlockListResult,
  ApiResponse,
  ReorderOutlineItemDto,
  BlockDTO,
  BlockType,
  ModelOption,
  SaveMdflowPayload,
  LessonCreationSettings,
} from '../types/shifu';
import api from '@/api';
import { debounce } from 'lodash';
import {
  createContext,
  ReactElement,
  ReactNode,
  useContext,
  useState,
  useCallback,
  useRef,
} from 'react';
import { LEARNING_PERMISSION } from '@/c-api/studyV2';
import {
  getStoredPreviewVariables,
  mapKeysToStoredVariables,
  PreviewVariablesMap,
  savePreviewVariables,
  StoredVariablesByScope,
} from '@/components/lesson-preview/variableStorage';
import { useTracking } from '@/c-common/hooks/useTracking';

const ShifuContext = createContext<ShifuContextType | undefined>(undefined);
const PROFILE_CACHE_TTL = 5_000; // 5s

const buildBlockListWithAllInfo = (
  blocks: Block[],
  blockTypes: Record<string, any>,
  blockProperties: Record<string, BlockDTO>,
) => {
  const list = blocks.map((block: Block) => {
    return {
      bid: block.bid,
      type: blockTypes[block.bid] ?? blockProperties[block.bid].type,
      properties: blockProperties[block.bid].properties,
      variable_bids: blockProperties[block.bid].variable_bids,
      resource_bids: blockProperties[block.bid].resource_bids,
    };
  });
  return list;
};

export const ShifuProvider = ({
  children,
}: {
  children: ReactNode;
}): ReactElement => {
  const { trackEvent } = useTracking();
  const [currentShifu, setCurrentShifu] = useState<Shifu | null>(null);
  const [chapters, setChapters] = useState<Outline[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [lastSaveTime, setLastSaveTime] = useState<Date | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focusId, setFocusId] = useState('');
  const [focusValue, setFocusValue] = useState('');
  const [cataData, setCataData] = useState<{ [x: string]: Outline }>({});
  const [blocks, setBlocks] = useState<BlockDTO[]>([]);
  const [blockProperties, setBlockProperties] = useState<{
    [x: string]: BlockDTO;
  }>({});
  const [blockContentProperties, setBlockContentProperties] = useState<{
    [x: string]: any;
  }>({});
  const [blockTypes, setBlockTypes] = useState<{
    [x: string]: BlockType;
  }>({});
  const [blockUITypes, setBlockUITypes] = useState<{
    [x: string]: BlockType;
  }>({});
  const [blockContentTypes, setBlockContentTypes] = useState<{
    [x: string]: BlockType;
  }>({});
  const [blockContentState, setBlockContentState] = useState<{
    [x: string]: 'edit' | 'preview';
  }>({});
  const [blockErrors, setBlockErrors] = useState<{
    [x: string]: string | null;
  }>({});
  const [currentNode, setCurrentNode] = useState<Outline | null>(null);
  const [profileItemDefinations, setProfileItemDefinations] = useState<
    ProfileItem[]
  >([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [mdflow, setMdflow] = useState<string>('');
  const [variables, setVariables] = useState<string[]>([]);
  const [hiddenVariables, setHiddenVariables] = useState<string[]>([]);
  const currentMdflow = useRef<string>('');
  const lastPersistedMdflowRef = useRef<Record<string, string>>({});
  const saveMdflowLockRef = useRef<{
    inflight: boolean;
    outlineId: string | null;
  }>({
    inflight: false,
    outlineId: null,
  });
  const mdflowRequestRef = useRef<{ id: number; outlineId: string | null }>({
    id: 0,
    outlineId: null,
  });
  const mdflowCacheRef = useRef<Record<string, string>>({});
  const profileDefinitionCacheRef = useRef<
    Record<
      string,
      { list: ProfileItem[]; systemVariableKeys: string[]; updatedAt: number }
    >
  >({});
  const [systemVariables, setSystemVariables] = useState<
    Record<string, string>[]
  >([]);
  const currentOutlineRef = useRef<string | null>(null);

  const internalSetCurrentNode = (node: Outline | null) => {
    setCurrentNode(node);
    currentOutlineRef.current = node?.bid || null;
    const cacheKey = node?.bid;
    if (cacheKey && mdflowCacheRef.current[cacheKey] !== undefined) {
      const cached = mdflowCacheRef.current[cacheKey];
      currentMdflow.current = cached;
      setMdflow(cached);
    }
  };
  // Debounced autosave for mdflow; kept stable via ref
  const debouncedAutoSaveRef = useRef(
    debounce(async (payload?: SaveMdflowPayload) => {
      await saveMdflow(payload);
    }, 3000),
  );

  // Ensure UI types and content types are fetched only in the client environment
  // const UITypes = useUITypes()

  const loadShifu = async (
    shifuId: string,
    options?: {
      silent?: boolean;
    },
  ) => {
    const silent = options?.silent ?? false;

    try {
      if (!silent) {
        setIsLoading(true);
      }
      setError(null);
      const shifu = await api.getShifuDetail({
        shifu_bid: shifuId,
      });
      setCurrentShifu(shifu);
    } catch (error) {
      console.error(error);
      setError('Failed to load shifu');
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  };
  const recursiveCataData = (cataTree: Outline[]): any => {
    const result: any = {};
    const processItem = (item: any, parentId = '', depth = 0) => {
      result[item.id] = {
        ...cataData[item.id],
        parent_bid: parentId,
        parentId: parentId,
        name: item.name,
        type: item.type,
        is_hidden: item.is_hidden,
        depth: depth,
        status: 'edit',
      };

      if (item.children) {
        item.children.forEach((child: any) => {
          processItem(child, item.bid, depth + 1);
        });
      }
    };

    cataTree.forEach((child: any) => {
      processItem(child, '', 0);
    });
    return result;
  };
  const buildOutlineTree = (items: Outline[]) => {
    const treeData = recursiveCataData(items);
    setCataData(treeData);
    return treeData;
  };
  const findNode = (id: string) => {
    const find = (nodes: Outline[]): any => {
      for (const node of nodes) {
        if (node.id === id) {
          return node;
        }
        if (node.children) {
          const result = find(node.children || []);
          if (result) {
            return result;
          }
        }
      }
      return null;
    };
    return find(chapters);
  };

  // Helper function to find the best node to select after deletion
  const findBestNodeAfterDeletion = (
    deletedOutline: Outline,
  ): Outline | null => {
    // If it's a chapter (depth 0), don't auto-select anything
    if ((deletedOutline.depth || 0) === 0) {
      return null;
    }

    // Find the parent node using parent_bid first
    let parent = findNode(deletedOutline.parent_bid || '');

    // If parent_bid is undefined or parent not found, search through all chapters to find the actual parent
    if (!parent) {
      for (const chapter of chapters) {
        const searchInNode = (node: Outline): Outline | null => {
          if (node.children) {
            for (const child of node.children) {
              if (child.id === deletedOutline.id) {
                return node; // Found the parent
              }
              const result = searchInNode(child);
              if (result) return result;
            }
          }
          return null;
        };
        const foundParent = searchInNode(chapter);
        if (foundParent) {
          parent = foundParent;
          break;
        }
      }
    }

    if (!parent?.children) {
      return null;
    }

    // Find the index of the deleted node in parent's children
    const deletedIndex = parent.children.findIndex(
      (child: any) => child.id === deletedOutline.id,
    );

    if (deletedIndex > 0) {
      // Select the previous sibling (the node above)
      return parent.children[deletedIndex - 1];
    } else if (deletedIndex === 0) {
      // If it's the first child, select the parent (chapter)
      return parent;
    }

    return null;
  };
  // Helper function to remove outline from tree structure
  const removeOutlineFromTree = (outline: Outline) => {
    if (outline.parent_bid) {
      const parent = findNode(outline.parent_bid || '');
      if (parent) {
        parent.children = parent.children?.filter(
          (child: any) => child.id !== outline.id,
        );
      }
    } else {
      const list = chapters.filter((child: any) => child.id !== outline.id);
      setChapters([...list]);
      return;
    }
    setChapters([...chapters]);
  };

  // Helper function to clean up catalog data
  const cleanupCatalogData = (outline: Outline) => {
    delete cataData[outline.id];
    setCataData({ ...cataData });
  };

  // Helper function to handle API deletion
  const deleteOutlineAPI = async (outline: Outline) => {
    if (outline.id === 'new_chapter') {
      return;
    }
    await api.deleteOutline({
      shifu_bid: currentShifu?.bid || '',
      outline_bid: outline.id,
    });
  };

  // Helper function to handle cursor positioning after deletion
  const handleCursorPositioning = async (nextNode: Outline | null) => {
    if (nextNode) {
      internalSetCurrentNode(nextNode);
      if (nextNode.bid) {
        // await loadBlocks(nextNode.bid, currentShifu?.bid || '');
        await loadMdflow(nextNode.bid, currentShifu?.bid || '');
      } else {
        setBlocks([]);
      }
    } else {
      internalSetCurrentNode(null);
      setBlocks([]);
    }
    setFocusId('');
  };

  // Remove placeholder nodes locally without hitting APIs
  const removePlaceholderOutline = (outline: Outline) => {
    removeOutlineFromTree(outline);
    cleanupCatalogData(outline);
    setFocusId('');
  };

  const removeOutline = async (outline: Outline) => {
    setIsSaving(true);
    setError(null);

    const isCurrentNodeDeleted = currentNode?.id === outline.id;
    const nextNode = isCurrentNodeDeleted
      ? findBestNodeAfterDeletion(outline)
      : null;

    try {
      removeOutlineFromTree(outline);
      cleanupCatalogData(outline);
      await deleteOutlineAPI(outline);

      if (isCurrentNodeDeleted) {
        await handleCursorPositioning(nextNode);
      }

      setLastSaveTime(new Date());
    } catch (error) {
      console.error(error);
      setError('Failed to remove outline');
    } finally {
      setIsSaving(false);
    }
  };

  const loadProfileItemDefinations = async (shifuId: string) => {
    const list = await api.getProfileItemDefinitions({
      parent_id: shifuId,
      type: 'all',
    });
    setProfileItemDefinations(list);
  };

  const remapOutlineTree = (items: any): Outline[] => {
    return items.map((item: any) => {
      return {
        id: item.bid,
        type: item.type,
        is_hidden: item.is_hidden,
        name: item.name,
        bid: item.bid,
        position: item.position,
        children: remapOutlineTree(item.children),
      };
    });
  };

  const loadMdflow = async (outlineId: string, shifuId: string) => {
    if (
      outlineId === '' ||
      outlineId === 'new_lesson' ||
      outlineId === 'new_chapter'
    ) {
      return;
    }
    const requestId = mdflowRequestRef.current.id + 1;
    mdflowRequestRef.current = { id: requestId, outlineId };
    setIsLoading(true);
    setError(null);
    const isLatest = () =>
      mdflowRequestRef.current.id === requestId &&
      mdflowRequestRef.current.outlineId === outlineId;

    try {
      const mdflow = await api.getMdflow({
        shifu_bid: shifuId,
        outline_bid: outlineId,
      });
      mdflowCacheRef.current[outlineId] = mdflow || '';
      if (!isLatest()) {
        return;
      }
      // Only apply to state if this outline is still the current one
      if (currentOutlineRef.current === outlineId) {
        setMdflow(mdflow);
        setCurrentMdflow(mdflow);
      }
      lastPersistedMdflowRef.current[outlineId] = mdflow || '';
      if (currentOutlineRef.current === outlineId) {
        await parseMdflow(mdflow, shifuId, outlineId);
      }
    } catch (error) {
      if (isLatest()) {
        console.error(error);
        setError('Failed to load chapters');
      }
    } finally {
      if (isLatest()) {
        setIsLoading(false);
      }
    }
  };

  const loadChapters = async (shifuId: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const [shifuInfo, chaptersData] = await Promise.all([
        api.getShifuDetail({ shifu_bid: shifuId }),
        api.getShifuOutlineTree({ shifu_bid: shifuId }),
      ]);
      setCurrentShifu(shifuInfo);
      const list = remapOutlineTree(chaptersData);
      if (list.length > 0) {
        // Find the first lesson to select by default
        const firstLesson = list.find(
          chapter => chapter.children && chapter.children.length > 0,
        )?.children?.[0];

        if (firstLesson) {
          internalSetCurrentNode({
            ...firstLesson,
            depth: 1,
          });
          await loadMdflow(firstLesson.bid, shifuId);
          // await loadBlocks(firstLesson.bid, shifuId);
        }
      }
      setChapters(list);
      buildOutlineTree(list);
      // loadProfileItemDefinations(shifuId);
    } catch (error) {
      console.error(error);
      setError('Failed to load chapters');
    } finally {
      setIsLoading(false);
    }
  };

  const initBlockTypes = async (list: Block[]) => {
    const types = list.reduce((prev: any, cur: Block) => {
      prev[cur.bid] = cur.type;
      return prev;
    }, {});
    setBlockTypes(types);
  };

  const initBlockProperties = async (list: Block[]) => {
    const properties = list.reduce((prev: any, cur: Block) => {
      return {
        ...prev,
        [cur.bid]: cur,
      };
    }, {});
    setBlockProperties(properties);
  };

  const updateBlockProperties = useCallback(
    async (bid: string, properties: any) => {
      setBlocks(prevBlocks =>
        prevBlocks.map(block =>
          block.bid === bid
            ? {
                ...block,
                type: properties.type,
                properties: properties.properties,
                variable_bids: properties.variable_bids || [],
                resource_bids: properties.resource_bids || [],
              }
            : block,
        ),
      );

      setBlockTypes(prev => ({
        ...prev,
        [bid]: properties.type,
      }));
      setBlockProperties(prev => {
        const newState = {
          ...prev,
          [bid]: properties,
        };
        return newState;
      });
    },
    [],
  );

  const loadBlocks = async (outlineId: string, shifuId: string) => {
    try {
      setIsLoading(true);
      setError(null);
      clearBlockErrors();
      const blocksData = await api.getBlocks({
        shifu_bid: shifuId,
        outline_bid: outlineId,
      });
      const list = blocksData;
      setBlocks(list);
      initBlockTypes(list);
      initBlockProperties(list);
      setIsLoading(false);
    } catch (error) {
      console.error(error);
      setIsLoading(false);
    }
  };
  const blockPropertiesRef = useRef(blockProperties);
  blockPropertiesRef.current = blockProperties;
  const saveBlocks = useCallback(
    async (shifu_id: string) => {
      if (isLoading) {
        return;
      }
      const list = buildBlockListWithAllInfo(
        blocks,
        blockTypes,
        blockPropertiesRef.current,
      );
      try {
        setError(null);
        await api.saveBlocks({
          shifu_bid: shifu_id,
          outline_bid: currentNode!.bid,
          blocks: list,
        });
      } catch (error) {
        console.error(error);
        setError('Failed to save blocks');
      }
    },
    [blocks, isLoading, blockTypes, currentNode],
  );

  const addSubOutline = async (
    parent: Outline,
    settings: LessonCreationSettings,
  ) => {
    const shifuBid = currentShifu?.bid;
    if (!shifuBid) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const parentNode = findNode(parent.id);
      if (!parentNode) {
        throw new Error('Parent node not found');
      }
      const parentId = parentNode.id;
      const index = parentNode.children?.length || 0;
      const created = await api.createOutline({
        parent_bid: parentId,
        index,
        name: settings.name,
        description: settings.name,
        type: settings.learningPermission,
        system_prompt: settings.systemPrompt,
        is_hidden: settings.isHidden,
        shifu_bid: shifuBid,
      });
      const depth = (parentNode.depth || parent.depth || 0) + 1;
      const newOutline: Outline = {
        id: created.bid,
        bid: created.bid,
        parent_bid: parentId,
        name: created.name,
        children: [],
        position: '',
        depth,
        type: settings.learningPermission,
        is_hidden: settings.isHidden,
      };
      parentNode.children = [...(parentNode.children || []), newOutline];
      setChapters([...chapters]);
      setCataData({
        ...cataData,
        [newOutline.id]: {
          ...newOutline,
          parentId: parentId,
          status: 'edit',
        },
      });
      trackEvent('creator_outline_create', {
        shifu_bid: shifuBid,
        outline_bid: newOutline.bid,
        outline_name: newOutline.name,
        parent_bid: parentId,
      });
      setLastSaveTime(new Date());
    } catch (error) {
      console.error(error);
      setError('Failed to create lesson');
      throw error;
    } finally {
      setIsSaving(false);
    }
  };

  const addRootOutline = async (settings: LessonCreationSettings) => {
    const shifuBid = currentShifu?.bid;
    if (!shifuBid) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const index = chapters.length;
      const created = await api.createOutline({
        parent_bid: '',
        index,
        name: settings.name,
        description: settings.name,
        type: LEARNING_PERMISSION.GUEST,
        system_prompt: settings.systemPrompt,
        is_hidden: false,
        shifu_bid: shifuBid,
      });
      const newOutline: Outline = {
        id: created.bid,
        bid: created.bid,
        parent_bid: '',
        name: created.name,
        children: [],
        position: '',
        depth: 0,
      };
      setChapters([...chapters, newOutline]);
      setCataData({
        ...cataData,
        [newOutline.id]: {
          ...newOutline,
          status: 'edit',
        },
      });
      trackEvent('creator_outline_create', {
        shifu_bid: shifuBid,
        outline_bid: newOutline.bid,
        outline_name: newOutline.name,
        parent_bid: '',
      });
      setLastSaveTime(new Date());
    } catch (error) {
      console.error(error);
      setError('Failed to create chapter');
      throw error;
    } finally {
      setIsSaving(false);
    }
  };

  const saveCurrentBlocks = useCallback(
    async (
      outline: string,
      blocks: Block[],
      blockTypes: Record<string, any>,
      blockProperties: Record<string, BlockDTO>,
      shifu_id: string,
    ): Promise<ApiResponse<SaveBlockListResult> | null> => {
      if (isLoading) {
        return null;
      }
      setIsSaving(true);
      setError(null);
      try {
        setError(null);
        const blockList = buildBlockListWithAllInfo(
          blocks,
          blockTypes,
          blockProperties,
        );
        const result = await api.saveBlocks({
          outline_bid: outline,
          blocks: blockList,
          shifu_bid: shifu_id || '',
        });

        if (!result) {
          setError('common.core.errorSaveFailed');
          return result;
        }

        const blockErrorMessages = result?.error_messages;
        const errorCount =
          blockErrorMessages && typeof blockErrorMessages === 'object'
            ? Object.keys(blockErrorMessages).length
            : 0;

        if (errorCount > 0) {
          Object.entries(blockErrorMessages).forEach(
            ([blockId, errorMessage]) => {
              setBlockError(blockId, errorMessage as string);
            },
          );
        } else {
          clearBlockErrors();
        }

        return result;
      } catch (error: any) {
        setError(error.message);
        throw error;
      } finally {
        setIsSaving(false);
        setLastSaveTime(new Date());
      }
    },
    [],
  );

  const autoSaveBlocks = (
    payload?: SaveMdflowPayload,
  ): Promise<ApiResponse<SaveBlockListResult> | null> => {
    debouncedAutoSaveRef.current(payload);
    return Promise.resolve(null);
  };

  const flushAutoSaveBlocks = (payload?: SaveMdflowPayload) => {
    if (payload) {
      debouncedAutoSaveRef.current(payload);
    }
    debouncedAutoSaveRef.current.flush();
  };

  const cancelAutoSaveBlocks = () => {
    debouncedAutoSaveRef.current.cancel();
  };

  const addSiblingOutline = async (
    item: Outline,
    settings: LessonCreationSettings,
  ) => {
    const shifuBid = currentShifu?.bid;
    if (!shifuBid) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const parentNode = findNode(item.parent_bid || '');
      if (!parentNode) {
        throw new Error('Parent node not found');
      }
      const parentId = parentNode.id;
      const currentIndex =
        parentNode.children?.findIndex(child => child.id === item.id) ?? -1;
      const insertIndex =
        currentIndex >= 0 ? currentIndex + 1 : parentNode.children?.length || 0;
      const created = await api.createOutline({
        parent_bid: parentId,
        index: insertIndex,
        name: settings.name,
        description: settings.name,
        type: settings.learningPermission,
        system_prompt: settings.systemPrompt,
        is_hidden: settings.isHidden,
        shifu_bid: shifuBid,
      });
      const depth =
        item.depth !== undefined ? item.depth : (parentNode.depth || 0) + 1;
      const newOutline: Outline = {
        id: created.bid,
        bid: created.bid,
        parent_bid: parentId,
        name: created.name,
        children: [],
        position: '',
        depth,
        type: settings.learningPermission,
        is_hidden: settings.isHidden,
      };
      const children = [...(parentNode.children || [])];
      children.splice(insertIndex, 0, newOutline);
      parentNode.children = children;
      setChapters([...chapters]);
      setCataData({
        ...cataData,
        [newOutline.id]: {
          ...newOutline,
          parentId: parentId,
          status: 'edit',
        },
      });
      trackEvent('creator_outline_create', {
        shifu_bid: shifuBid,
        outline_bid: newOutline.bid,
        outline_name: newOutline.name,
        parent_bid: parentId,
      });
      setLastSaveTime(new Date());
    } catch (error) {
      console.error(error);
      setError('Failed to create lesson');
      throw error;
    } finally {
      setIsSaving(false);
    }
  };

  const createChapter = async (data: Outline) => {
    setIsSaving(true);
    setError(null);
    updateOutlineStatus(data.id, 'saving');
    const index = chapters.findIndex(child => child.id === data.id);

    try {
      if (data.id === 'new_chapter') {
        const newChapter = await api.createOutline({
          parent_bid: '',
          index: index,
          name: data.name,
          description: data.name,
          type: LEARNING_PERMISSION.GUEST,
          system_prompt: '',
          is_hidden: false,
          shifu_id: currentShifu?.bid || '',
        });
        replaceOutline('new_chapter', {
          id: newChapter.bid,
          bid: newChapter.bid,
          name: newChapter.name,
          position: '',
          children: [],
        });
        trackEvent('creator_outline_create', {
          shifu_bid: currentShifu?.bid || '',
          outline_bid: newChapter.bid,
          outline_name: newChapter.name,
          parent_bid: data.parent_bid || '',
        });
        setFocusId('');
        setLastSaveTime(new Date());
      } else {
        await api.modifyOutline({
          outline_bid: data.id,
          index: index,
          description: data.name,
          name: data.name,
          shifu_id: currentShifu?.bid || '',
        });

        const currentChapter = chapters.find(chapter => chapter.id === data.id);

        replaceOutline(data.id, {
          id: data.id,
          bid: data.bid,
          name: data.name,
          position: '',
          children: currentChapter?.children || [],
        });
        setFocusId('');
        setLastSaveTime(new Date());
      }
    } catch (error) {
      console.error(error);
      setError(
        data.id === 'new_chapter'
          ? 'Failed to create chapter'
          : 'Failed to modify chapter',
      );
      updateOutlineStatus(data.id, data.id === 'new_chapter' ? 'new' : 'edit');
      setFocusId(data.id);
    } finally {
      setIsSaving(false);
      setIsLoading(false);
    }
  };

  const createOutline = async (data: Outline) => {
    setIsSaving(true);
    setError(null);
    updateOutlineStatus(data.bid, 'saving');

    const parent = findNode(data.parent_bid || '');
    const index =
      parent?.children?.findIndex((child: Outline) => child.bid === data.bid) ||
      0;

    const isNew = data.bid === 'new_chapter' || data.bid === 'new_lesson';
    try {
      if (isNew) {
        const type =
          data.bid === 'new_chapter'
            ? LEARNING_PERMISSION.GUEST
            : LEARNING_PERMISSION.TRIAL;
        const newUnit = await api.createOutline({
          parent_bid: data.parent_bid,
          index,
          name: data.name,
          description: data.name,
          type: type,
          system_prompt: '',
          is_hidden: false,
          shifu_bid: currentShifu?.bid || '',
        });

        replaceOutline(data.bid, {
          id: newUnit.bid,
          bid: newUnit.bid,
          name: newUnit.name,
          position: '',
          children: [],
        });

        trackEvent('creator_outline_create', {
          shifu_bid: currentShifu?.bid || '',
          outline_bid: newUnit.bid,
          outline_name: newUnit.name,
          parent_bid: data.parent_bid || '',
        });
        setFocusId('');
        setLastSaveTime(new Date());
      } else {
        await api.modifyOutline({
          outline_bid: data.id,
          index: index,
          description: data.name,
          name: data.name,
          shifu_bid: currentShifu?.bid || '',
        });
        replaceOutline(data.id, {
          id: data.id,
          bid: data.bid,
          name: data.name,
          position: data.position,
        });
        setFocusId('');
        setLastSaveTime(new Date());
      }
    } catch (error) {
      console.error(error);
      setError(
        data.id === 'new_chapter'
          ? 'Failed to create unit'
          : 'Failed to modify unit',
      );
      updateOutlineStatus(data.id, data.id === 'new_chapter' ? 'new' : 'edit');
      setFocusId(data.id);
    } finally {
      setIsSaving(false);
      setIsLoading(false);
    }
  };

  const createSiblingUnit = async (data: Outline) => {
    try {
      updateOutlineStatus(data.id, 'saving');
      setError(null);

      const parent = findNode(data.parent_bid || '');
      // get node index in children
      const index = parent.children.findIndex(
        (child: Outline) => child.id === data.id,
      );

      const newUnit = await api.createOutline({
        parent_bid: data.parent_bid,
        index: Math.max(0, index - 1),
        name: data.name,
        description: data.name,
        type: LEARNING_PERMISSION.TRIAL,
        system_prompt: '',
        is_hidden: false,
        shifu_id: currentShifu?.bid || '',
      });

      replaceOutline('new_chapter', {
        id: newUnit.bid,
        parent_bid: parent.bid,
        bid: newUnit.bid,
        name: newUnit.name,
        position: '',
        children: [],
      });
    } catch (error) {
      console.error(error);
      setError('Failed to create chapter');
    } finally {
      setIsLoading(false);
    }
  };

  const updateOutlineStatus = (
    id: string,
    status: 'new' | 'edit' | 'saving',
  ) => {
    setCataData({
      ...cataData,
      [id]: {
        ...cataData[id],
        status,
      },
    });
  };

  const updateOutline = async (id: string, value: Outline) => {
    setCataData({
      ...cataData,
      [id]: {
        ...cataData[id],
        ...value,
      },
    });
    setLastSaveTime(new Date());
  };

  const addChapter = async (chapter: Outline) => {
    if (cataData['new_chapter']) {
      return;
    }
    if (chapters?.find((child: any) => child.id === 'new_chapter')) {
      return;
    }
    setChapters([...chapters, chapter]);
    updateOutline(chapter.id, {
      ...chapter,
      status: 'new',
    });
    setFocusId(chapter.id);
  };

  const replaceOutline = async (id: string, outline: Outline) => {
    const node = findNode(id);
    node.id = outline.id;
    node.name = outline.name;
    node.position = outline.position;
    node.parent_bid = outline.parent_bid;
    node.bid = outline.bid;
    if (outline.children && outline.children.length > 0) {
      node.children = outline.children;
    }
    setChapters([...chapters]);
    delete cataData[id];
    setCataData({
      ...cataData,
      [outline.id]: {
        ...outline,
        status: 'edit',
      },
    });
  };

  const setBlockContentPropertiesById = (
    id: string,
    properties: AIBlockProperties | SolidContentBlockProperties,
    reset: boolean = false,
  ) => {
    if (reset) {
      setBlockContentProperties({
        ...blockContentProperties,
        [id]: properties,
      });
      return;
    }
    setBlockContentProperties({
      ...blockContentProperties,
      [id]: {
        ...properties,
      },
    });
  };

  const setBlockContentTypesById = (id: string, type: BlockType) => {
    setBlockTypes({
      ...blockTypes,
      [id]: type,
    });
  };

  const setBlockUIPropertiesById = (
    id: string,
    properties: any,
    reset: boolean = false,
  ) => {
    if (reset) {
      setBlockProperties({
        ...blockProperties,
        [id]: properties,
      });
      return;
    }
    setBlockProperties({
      ...blockProperties,
      [id]: {
        ...blockProperties[id],
        ...properties,
      },
    });
    if (blockProperties[id].type !== properties.type) {
      setBlockTypes({
        ...blockTypes,
        [id]: properties.type,
      });
    }
  };

  const setBlockUITypesById = (id: string, type: BlockType) => {
    setBlockTypes({
      ...blockTypes,
      [id]: type,
    });
  };

  const setBlockContentStateById = (id: string, state: 'edit' | 'preview') => {
    setBlockContentState({
      ...blockContentState,
      [id]: state,
    });
  };

  const updateChapterOrder = async (
    move_chapter_id: string,
    move_to_parent_id?: string,
    chapter_ids?: string[],
  ) => {
    setIsSaving(true);
    setError(null);
    try {
      await api.updateChapterOrder({
        move_chapter_id,
        move_to_parent_id,
        chapter_ids,
        shifu_id: currentShifu?.bid,
      });
      setLastSaveTime(new Date());
    } catch (error) {
      console.error(error);
      setError('Failed to update chapter order');
    } finally {
      setIsSaving(false);
    }
  };

  const removeBlock = async (id: string) => {
    const list = blocks.filter(block => block.bid !== id);
    setBlocks(list);
    await saveCurrentBlocks(
      currentNode!.bid,
      list,
      blockTypes,
      blockProperties,
      currentShifu?.bid || '',
    );
  };

  const normalizeModelOptions = (list: any): ModelOption[] => {
    if (!Array.isArray(list)) return [];
    const seen = new Set<string>();
    const options: ModelOption[] = [];

    list.forEach(item => {
      if (typeof item === 'string') {
        const value = item.trim();
        if (value && !seen.has(value)) {
          seen.add(value);
          options.push({ value, label: value });
        }
        return;
      }

      if (item && typeof item === 'object') {
        const value = String(item.model || item.value || '').trim();
        if (!value || seen.has(value)) {
          return;
        }
        const labelSource =
          item.display_name || item.displayName || item.label || value;
        const label = String(labelSource || value).trim() || value;
        seen.add(value);
        options.push({ value, label });
      }
    });

    return options;
  };

  const loadModels = async () => {
    const list = await api.getModelList({});
    setModels(normalizeModelOptions(list));
  };

  const setBlockError = (blockId: string, error: string | null) => {
    setBlockErrors(prev => ({
      ...prev,
      [blockId]: error,
    }));
  };

  const clearBlockErrors = () => {
    setBlockErrors({});
  };

  const reorderOutlineTree = async (outlines: ReorderOutlineItemDto[]) => {
    await api.reorderOutlineTree({
      shifu_bid: currentShifu?.bid || '',
      outlines,
    });
  };

  const applyProfileDefinitionList = (
    list: ProfileItem[],
    shifuId?: string,
  ): { list: ProfileItem[]; systemVariableKeys: string[] } => {
    setProfileItemDefinations(list || []);
    const sysVariables =
      list
        ?.filter((item: ProfileItem) => item.profile_scope === 'system')
        .map((item: ProfileItem) => ({
          name: item.profile_key,
          label: item.profile_remark,
        })) || [];
    setSystemVariables(sysVariables);

    const customVariables =
      list
        ?.filter(
          (item: ProfileItem) =>
            item.profile_scope === 'user' && !item.is_hidden,
        )
        .map((item: ProfileItem) => item.profile_key) || [];
    const hiddenVariableKeys =
      list
        ?.filter(
          (item: ProfileItem) =>
            item.profile_scope === 'user' && item.is_hidden,
        )
        .map((item: ProfileItem) => item.profile_key) || [];

    setVariables(customVariables);
    setHiddenVariables(hiddenVariableKeys);

    const systemVariableKeys = sysVariables.map(variable => variable.name);
    if (shifuId) {
      profileDefinitionCacheRef.current[shifuId] = {
        list,
        systemVariableKeys,
        updatedAt: Date.now(),
      };
    }

    return {
      list: list || [],
      systemVariableKeys,
    };
  };

  const refreshProfileDefinitions = useCallback(async (shifuId: string) => {
    const cached = profileDefinitionCacheRef.current[shifuId];
    const now = Date.now();
    if (cached && now - cached.updatedAt < PROFILE_CACHE_TTL) {
      applyProfileDefinitionList(cached.list, shifuId);
      return cached;
    }
    try {
      const list = await api.getProfileItemDefinitions({
        parent_id: shifuId,
        type: 'all',
      });
      return applyProfileDefinitionList(list || [], shifuId);
    } catch (error) {
      console.error(error);
      setProfileItemDefinations([]);
      setSystemVariables([]);
      setVariables([]);
      setHiddenVariables([]);
      throw error;
    }
  }, []);

  const parseMdflow = async (
    value: string,
    shifuId: string,
    outlineId: string,
  ) => {
    setIsLoading(true);
    try {
      await refreshProfileDefinitions(shifuId);
    } catch (error) {
      console.error(error);
      setSystemVariables([]);
      setVariables([]);
      setHiddenVariables([]);
    } finally {
      setIsLoading(false);
    }
  };

  const previewParse = async (
    value: string,
    shifuId: string,
    outlineId: string,
  ): Promise<{
    variables: PreviewVariablesMap;
    blocksCount: number;
    systemVariableKeys: string[];
  }> => {
    try {
      const resolvedShifuId = shifuId || currentShifu?.bid || '';
      const resolvedOutlineId = outlineId || currentNode?.bid || '';
      const { systemVariableKeys } =
        (await refreshProfileDefinitions(resolvedShifuId)) || {};
      const result = await api.parseMdflow({
        shifu_bid: resolvedShifuId,
        outline_bid: resolvedOutlineId,
        data: value,
      });
      const variableKeys = result?.variables || [];
      const resolvedSystemKeys =
        systemVariableKeys && systemVariableKeys.length
          ? systemVariableKeys
          : systemVariables?.map(variable => variable.name).filter(Boolean) ||
            [];
      const storedVariables: StoredVariablesByScope =
        getStoredPreviewVariables(resolvedShifuId);
      const variablesMap = mapKeysToStoredVariables(
        variableKeys,
        storedVariables,
        resolvedSystemKeys,
      );
      savePreviewVariables(resolvedShifuId, variablesMap, resolvedSystemKeys);
      return {
        variables: variablesMap,
        blocksCount: result?.blocks_count ?? 0,
        systemVariableKeys: resolvedSystemKeys,
      };
    } catch (error) {
      console.error(error);
      return { variables: {}, blocksCount: 0, systemVariableKeys: [] };
    }
  };

  const hideUnusedVariables = async (shifuId: string, outlineId?: string) => {
    try {
      const list = await api.hideUnusedProfileItems({
        parent_id: shifuId,
        outline_id: outlineId,
      });
      if (list) {
        applyProfileDefinitionList(list as ProfileItem[], shifuId);
      } else {
        await refreshProfileDefinitions(shifuId);
      }
    } catch (error) {
      console.error(error);
    }
  };

  const restoreHiddenVariables = async (shifuId: string) => {
    try {
      if (!hiddenVariables.length) {
        return;
      }
      const list = await api.updateProfileHiddenState({
        parent_id: shifuId,
        profile_keys: hiddenVariables,
        hidden: false,
      });
      if (list) {
        applyProfileDefinitionList(list as ProfileItem[], shifuId);
      } else {
        await refreshProfileDefinitions(shifuId);
      }
    } catch (error) {
      console.error(error);
    }
  };

  const saveMdflow = async (payload?: SaveMdflowPayload) => {
    const shifu_bid = payload?.shifu_bid ?? currentShifu?.bid ?? '';
    const outline_bid = payload?.outline_bid ?? (currentNode?.bid || '');
    const data = payload?.data ?? currentMdflow.current;
    if (saveMdflowLockRef.current.inflight) {
      if (outline_bid && saveMdflowLockRef.current.outlineId !== outline_bid) {
        // When another outline save is in-flight, skip cross-outline saves
        console.log(
          'outline save is in-flight, skip cross-outline saves',
          saveMdflowLockRef.current.outlineId,
        );
        return;
      }
    }
    saveMdflowLockRef.current = {
      inflight: true,
      outlineId: outline_bid || null,
    };
    try {
      await api.saveMdflow({
        shifu_bid,
        outline_bid,
        data,
      });
      if (outline_bid) {
        mdflowCacheRef.current[outline_bid] = data || '';
        lastPersistedMdflowRef.current[outline_bid] = data || '';
      }
      setLastSaveTime(new Date());
    } finally {
      saveMdflowLockRef.current = { inflight: false, outlineId: null };
    }
  };

  const setCurrentMdflow = (value: string) => {
    currentMdflow.current = value;
    setMdflow(value || '');
    if (currentOutlineRef.current) {
      mdflowCacheRef.current[currentOutlineRef.current] = value || '';
    }
  };

  const getCurrentMdflow = () => {
    return currentMdflow.current;
  };

  const hasUnsavedMdflow = (outlineId?: string, value?: string) => {
    const targetOutlineId = outlineId || currentOutlineRef.current || '';
    if (!targetOutlineId) {
      return false;
    }
    const latest = value ?? currentMdflow.current ?? '';
    const last = lastPersistedMdflowRef.current[targetOutlineId] ?? '';
    return latest !== last;
  };

  const removePlaceholderLessons = (nodes: Outline[] = []): Outline[] => {
    return nodes
      .filter(node => node.id !== 'new_lesson')
      .map(node => ({
        ...node,
        children: removePlaceholderLessons(node.children || []),
      }));
  };

  const findNodeInList = (nodes: Outline[], id: string): Outline | null => {
    for (const node of nodes) {
      if (node.id === id) return node;
      const found = findNodeInList(node.children || [], id);
      if (found) return found;
    }
    return null;
  };

  const insertPlaceholderChapter = () => {
    if (chapters.some(ch => ch.id === 'new_chapter')) return;

    const placeholder: Outline = {
      id: 'new_chapter',
      bid: 'new_chapter',
      name: '',
      parent_bid: '',
      children: [],
      depth: 0,
      position: '',
      type: LEARNING_PERMISSION.GUEST,
      is_hidden: false,
    };

    setChapters([...chapters, placeholder]);

    setCataData({
      ...cataData,
      ['new_chapter']: {
        ...placeholder,
        parentId: '',
        status: 'new',
      },
    });

    setFocusId('new_chapter');
  };

  const insertPlaceholderLesson = (parent: Outline) => {
    if (!parent) return;

    let addedPlaceholder: Outline | null = null;
    let placeholderParentId: string | null = null;

    setChapters(prev => {
      const cleaned = removePlaceholderLessons(prev);
      const parentNode = findNodeInList(cleaned, parent.id);
      if (!parentNode) {
        return cleaned;
      }

      if (parentNode.children?.some(ch => ch.id === 'new_lesson')) {
        return cleaned;
      }

      const placeholder: Outline = {
        id: 'new_lesson',
        bid: 'new_lesson',
        name: '',
        parent_bid: parentNode.id,
        children: [],
        depth: (parentNode.depth || parent.depth || 0) + 1,
        position: '',
        type: LEARNING_PERMISSION.GUEST,
        is_hidden: false,
      };

      parentNode.children = [...(parentNode.children || []), placeholder];
      addedPlaceholder = placeholder;
      placeholderParentId = parentNode.id;
      return cleaned;
    });

    // prevent duplicate placeholder lesson
    setCataData(prev => {
      const next = { ...prev };
      delete next['new_lesson'];
      if (addedPlaceholder && placeholderParentId) {
        next['new_lesson'] = {
          ...addedPlaceholder,
          parentId: placeholderParentId,
          status: 'new',
        };
      }
      return next;
    });

    if (addedPlaceholder) {
      setFocusId('new_lesson');
    }
  };

  const value: ShifuContextType = {
    currentShifu,
    chapters,
    isLoading,
    isSaving,
    error,
    lastSaveTime,
    focusId,
    focusValue,
    cataData,
    blocks,
    blockContentProperties,
    blockTypes,
    blockContentState,
    blockErrors,
    currentNode,
    profileItemDefinations,
    models,
    blockProperties,
    blockUITypes,
    blockContentTypes,
    mdflow,
    variables,
    hiddenVariables,
    systemVariables,
    actions: {
      setFocusId,
      addChapter,
      addRootOutline,
      setChapters,
      loadShifu,
      loadChapters,
      createChapter,
      setFocusValue,
      updateOutline,
      addSubOutline,
      addSiblingOutline,
      removeOutline,
      replaceOutline,
      createSiblingUnit,
      createOutline,
      loadBlocks,
      updateBlockProperties,
      setBlockContentPropertiesById,
      setBlockContentTypesById,
      setBlockUIPropertiesById,
      setBlockUITypesById,
      updateChapterOrder,
      setBlockContentStateById,
      setBlocks,
      saveBlocks,
      autoSaveBlocks,
      saveCurrentBlocks,
      removeBlock,
      setCurrentNode: internalSetCurrentNode,
      loadModels,
      setBlockError,
      clearBlockErrors,
      reorderOutlineTree,
      loadMdflow,
      saveMdflow,
      parseMdflow,
      previewParse,
      hideUnusedVariables,
      restoreHiddenVariables,
      unhideVariablesByKeys: async (shifuId: string, keys: string[]) => {
        if (!keys.length) return;
        try {
          const list = await api.updateProfileHiddenState({
            parent_id: shifuId,
            profile_keys: keys,
            hidden: false,
          });
          if (list) {
            applyProfileDefinitionList(list as ProfileItem[], shifuId);
          } else {
            await refreshProfileDefinitions(shifuId);
          }
        } catch (error) {
          console.error(error);
        }
      },
      refreshProfileDefinitions,
      setCurrentMdflow,
      getCurrentMdflow,
      hasUnsavedMdflow,
      flushAutoSaveBlocks,
      cancelAutoSaveBlocks,
      insertPlaceholderChapter,
      insertPlaceholderLesson,
      removePlaceholderOutline,
    },
  };

  return (
    <ShifuContext.Provider value={value}>{children}</ShifuContext.Provider>
  );
};

export const useShifu = (): ShifuContextType => {
  const context = useContext(ShifuContext);
  if (context === undefined) {
    throw new Error('useShifu must be used within a ShifuProvider');
  }
  return context;
};

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
  ReorderOutlineItemDto
} from '../types/shifu'
import api from '@/api'
import { useContentTypes } from '@/components/render-block'
import { useUITypes } from '@/components/render-ui'
import { debounce } from 'lodash'
import {
  createContext,
  ReactNode,
  useContext,
  useState,
  useCallback
} from 'react'

const ShifuContext = createContext<ShifuContextType | undefined>(undefined)

const buildBlockListWithAllInfo = (
  blocks: Block[],
  blockContentTypes: Record<string, any>,
  blockContentProperties: Record<string, any>,
  blockUITypes: Record<string, any>,
  blockUIProperties: Record<string, any>
) => {
  const list = blocks.map((block: Block, index) => {
    return {
      properties: {
        block_id: block.properties.block_id,
        block_no: '',
        block_name: '',
        block_desc: '',
        block_type: 101,
        block_index: index,
        block_content: {
          type: blockContentTypes[block.properties.block_id],
          properties: blockContentProperties[block.properties.block_id]
        },
        block_ui: {
          type: blockUITypes[block.properties.block_id],
          properties: blockUIProperties[block.properties.block_id]
        }
      },
      type: 'block'
    }
  })
  return list
}

export const ShifuProvider: React.FC<{ children: ReactNode }> = ({
  children
}) => {
  const [currentShifu, setCurrentShifu] = useState<Shifu | null>(null)
  const [chapters, setChapters] = useState<Outline[]>([])
  const [isSaving, setIsSaving] = useState(false)
  const [lastSaveTime, setLastSaveTime] = useState<Date | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [focusId, setFocusId] = useState('')
  const [focusValue, setFocusValue] = useState('')
  const [cataData, setCataData] = useState<{ [x: string]: Outline }>({})
  const [blocks, setBlocks] = useState<Block[]>([])
  const [blockContentProperties, setBlockContentProperties] = useState<{
    [x: string]: any
  }>({})
  const [blockContentTypes, setBlockContentTypes] = useState<{
    [x: string]: string
  }>({})
  const [blockUIProperties, setBlockUIProperties] = useState<{
    [x: string]: any
  }>({})
  const [blockUITypes, setBlockUITypes] = useState<{ [x: string]: string }>({})
  const [blockContentState, setBlockContentState] = useState<{
    [x: string]: 'edit' | 'preview'
  }>({})
  const [blockErrors, setBlockErrors] = useState<{
    [x: string]: string | null
  }>({})
  const [currentNode, setCurrentNode] = useState<Outline | null>(null)
  const [profileItemDefinations, setProfileItemDefinations] = useState<
    ProfileItem[]
  >([])
  const [models, setModels] = useState<string[]>([])

  // 确保在客户端环境下获取 UI 类型和内容类型
  const UITypes = useUITypes()
  const ContentTypes = useContentTypes()

  const loadShifu = async (shifuId: string) => {
    try {
      setIsLoading(true)
      setError(null)
      const shifu = await api.getShifuDetail({
        shifu_bid: shifuId
      })
      setCurrentShifu(shifu)
    } catch (error) {
      console.error(error)
      setError('Failed to load shifu')
    } finally {
      setIsLoading(false)
    }
  }
  const recursiveCataData = (cataTree: Outline[]): any => {
    const result: any = {}
    const processItem = (item: any, parentId = '', depth = 0) => {
      result[item.id] = {
        ...cataData[item.id],
        parent_bid: parentId,
        parentId: parentId,
        name: item.name,
        depth: depth,
        status: 'edit'
      }

      if (item.children) {
        item.children.forEach((child: any) => {
          processItem(child, item.bid, depth + 1)
        })
      }
    }

    cataTree.forEach((child: any) => {
      processItem(child, '', 0)
    })
    return result
  }
  const buildOutlineTree = (items: Outline[]) => {
    const treeData = recursiveCataData(items)
    setCataData(treeData)
    return treeData
  }
  const findNode = (id: string) => {
    const find = (nodes: Outline[]): any => {
      for (let i = 0; i < nodes.length; i++) {
        if (nodes[i].id === id) {
          return nodes[i]
        }
        if (nodes[i].children) {
          const result = find(nodes[i].children || [])
          if (result) {
            return result
          }
        }
      }
      return null
    }
    return find(chapters)
  }
  const removeOutline = async (outline: Outline) => {
    setIsSaving(true)
    setError(null)
    try {
      console.log('removeOutline', outline)
      if (outline.parent_bid) {
        const parent = findNode(outline.parent_bid || '')
        if (parent) {
          parent.children = parent.children?.filter(
            (child: any) => child.id !== outline.id
          )
        }

        setChapters([...chapters])

        delete cataData[outline.id]
        setCataData({
          ...cataData
        })
        if (outline.id == 'new_chapter') {
          return
        }
          await api.deleteOutline({
            shifu_bid: currentShifu?.bid || '',
            outline_bid: outline.id
        })
      } else {
        const list = chapters.filter((child: any) => child.id !== outline.id)
        setChapters([...list])

        delete cataData[outline.id]
        setCataData({
          ...cataData
        })

        if (outline.id == 'new_chapter') {
          return
        }
        await api.deleteOutline({
          shifu_bid: currentShifu?.bid || '',
          outline_bid: outline.id
        })
      }
      setLastSaveTime(new Date())
    } catch (error) {
      console.error(error)
      setError('Failed to remove outline')
    } finally {
      setIsSaving(false)
    }
  }

  const loadProfileItemDefinations = async (shifuId: string) => {
    const list = await api.getProfileItemDefinitions({
      parent_id: shifuId,
      type: 'all'
    })
    setProfileItemDefinations(list)
  }


  const remapOutlineTree = (items: any): Outline[] => {
    return items.map((item: any) => {
      return {
        id: item.bid,
        name: item.name,
        bid: item.bid,
        position: item.position,
        children: remapOutlineTree(item.children)
      }
    })
  }

  const loadChapters = async (shifuId: string) => {
    try {
      setIsLoading(true)
      setError(null)
      const shifuInfo = await api.getShifuDetail({ shifu_bid: shifuId })
      setCurrentShifu(shifuInfo)
      const chaptersData = await api.getShifuOutlineTree({ shifu_bid: shifuId })

      const list = remapOutlineTree(chaptersData)
      if (list.length > 0) {
        if (list[0].children && list[0].children.length > 0) {
          setCurrentNode({
            ...list[0].children[0],
            depth: 1
          })
          await loadBlocks(list[0].children[0].bid, shifuId)
        }
      }
      setChapters(list)
      buildOutlineTree(list)
      loadProfileItemDefinations(shifuId)
    } catch (error) {
      console.error(error)
      setError('Failed to load chapters')
    } finally {
      setIsLoading(false)
    }
  }
  const initBlockContentTypes = async (list: Block[]) => {
    const types = list.reduce((prev: any, cur: Block) => {
      prev[cur.properties.block_id] = cur.properties.block_content.type
      return prev
    }, {})
    setBlockContentTypes(types)
  }

  const initBlockContentProperties = async (list: Block[]) => {
    const properties = list.reduce((prev: any, cur: Block) => {
      return {
        ...prev,
        [cur.properties.block_id]: cur.properties.block_content.properties
      }
    }, {})
    setBlockContentProperties(properties)
  }
  const initBlockUITypes = async (list: Block[]) => {
    const types = list.reduce((prev: any, cur: Block) => {
      prev[cur.properties.block_id] = cur.properties.block_ui.type
      return prev
    }, {})
    setBlockUITypes(types)
  }

  const initBlockUIProperties = async (list: Block[]) => {
    const properties = list.reduce((prev: any, cur: Block) => {
      return {
        ...prev,
        [cur.properties.block_id]: cur.properties.block_ui.properties
      }
    }, {})
    setBlockUIProperties(properties)
  }

  const buildBlockList = (blocks: Block[]) => {
    const list = blocks.map((block: Block, index) => {
      return {
        properties: {
          block_id: block.properties.block_id,
          block_no: '',
          block_name: '',
          block_desc: '',
          block_type: 101,
          block_index: index,
          block_content: {
            type: blockContentTypes[block.properties.block_id],
            properties: blockContentProperties[block.properties.block_id]
          },
          block_ui: {
            type: blockUITypes[block.properties.block_id],
            properties: blockUIProperties[block.properties.block_id]
          }
        },
        type: 'block'
      }
    })
    return list
  }

  const loadBlocks = async (outlineId: string, shifuId: string) => {
    try {
      setIsLoading(true)
      setError(null)
      clearBlockErrors()
      const blocksData = await api.getBlocks({
        shifu_bid: shifuId,
        outline_bid: outlineId
      })
      const list = blocksData.filter(p => p.type == 'block') as Block[]
      setBlocks(list)
      initBlockContentTypes(list)
      initBlockContentProperties(list)
      const blockUIList = list.filter(p => p.properties.block_ui)
      initBlockUITypes(blockUIList)
      initBlockUIProperties(blockUIList)
      setIsLoading(false)
    } catch (error) {
      console.error(error)
      setError('Failed to load blocks')
      setIsLoading(false)
    }
  }
  const saveBlocks = async (shifu_id: string) => {
    if (isLoading) {
      return
    }
    const list = buildBlockList(blocks)
    try {
      setError(null)
      console.log('saveBlocks', shifu_id, currentNode)
      await api.saveBlocks({
        shifu_bid: shifu_id,
        outline_bid: currentNode!.bid,
        blocks: list
      })
    } catch (error) {
      console.error(error)
      setError('Failed to save blocks')
    }
  }
  const addBlock = async (
    index: number,
    blockType: string = 'ai',
    shifu_id: string
  ) => {
    setIsSaving(true)
    setError(null)
    try {
      const item = ContentTypes.find(p => p.type == blockType)
      const buttonUI = UITypes[0]

      const block = await api.addBlock({
        block: {
          block_content: {
            type: blockType,
            properties: item?.properties
          },
          block_desc: '',
          block_index: index,
          block_name: '',
          block_no: '',
          block_type: 0,
          block_ui: buttonUI
        },
        block_index: index,
        outline_bid: currentNode!.bid,
        shifu_bid: shifu_id
      })

      blocks.splice(index, 0, block)
      const list = [...blocks]
      setBlockContentTypes({
        ...blockContentTypes,
        [block.properties.block_id]: blockType
      })
      setBlockContentProperties({
        ...blockContentProperties,
        [block.properties.block_id]: item?.properties
      })
      setBlockUITypes({
        ...blockUITypes,
        [block.properties.block_id]: buttonUI.type
      })
      setBlockUIProperties({
        ...blockUIProperties,
        [block.properties.block_id]: buttonUI.properties
      })
      setBlockContentStateById(block.properties.block_id, 'edit')
      setBlocks(list)
      setLastSaveTime(new Date())

      setTimeout(() => {
        document.getElementById(block.properties.block_id)?.scrollIntoView({
          behavior: 'smooth'
        })
      }, 500)
    } catch (error) {
      console.error(error)
      setError('Failed to add block')
    } finally {
      setIsSaving(false)
    }
  }
  const addSubOutline = async (parent: Outline, name = '') => {
    if (cataData['new_chapter']) {
      return
    }
    if (parent.children?.find((child: any) => child.id === 'new_chapter')) {
      return
    }
    const id = 'new_chapter'
    parent.children?.push({
      id,
      bid: id,
      parent_bid: parent.id,
      name: name,
      children: [],
      position: '',
      depth: (parent?.depth || 0) + 1
    })

    updateOuline(id, {
      parent_bid: parent.id,
      id,
      bid: id,
      name: name,
      children: [],
      position: '',
      depth: (parent?.depth || 0) + 1
    })

    setChapters([...chapters])

    setFocusId(id)
  }

  const saveCurrentBlocks = useCallback(
    async (
      outline: string,
      blocks: Block[],
      blockContentTypes: Record<string, any>,
      blockContentProperties: Record<string, any>,
      blockUITypes: Record<string, any>,
      blockUIProperties: Record<string, any>,
      shifu_id: string
    ): Promise<ApiResponse<SaveBlockListResult> | null> => {
      if (isLoading) {
        return null
      }
      setIsSaving(true)
      setError(null)
      try {
        setError(null)
        const blockList = buildBlockListWithAllInfo(
          blocks,
          blockContentTypes,
          blockContentProperties,
          blockUITypes,
          blockUIProperties
        )
        const result = await api.saveBlocks({
          outline_bid: outline,
          blocks: blockList,
          shifu_bid: shifu_id || ''
        })

        if (!result) {
          setError('common.error.save.failed')
          return result
        }

        const blockErrorMessages = result?.error_messages
        const errorCount =
          blockErrorMessages && typeof blockErrorMessages === 'object'
            ? Object.keys(blockErrorMessages).length
            : 0

        if (errorCount > 0) {
          Object.entries(blockErrorMessages).forEach(
            ([blockId, errorMessage]) => {
              setBlockError(blockId, errorMessage as string)
            }
          )
        } else {
          clearBlockErrors()
        }

        return result
      } catch (error: any) {
        setError(error.message)
        throw error
      } finally {
        setIsSaving(false)
        setLastSaveTime(new Date())
      }
    },
    []
  )

  const autoSaveBlocks = useCallback(
    debounce(
      async (
        outline: string,
        blocks: Block[],
        blockContentTypes: Record<string, any>,
        blockContentProperties: Record<string, any>,
        blockUITypes: Record<string, any>,
        blockUIProperties: Record<string, any>,
        shifu_id: string
      ) => {
        return await saveCurrentBlocks(
          outline,
          blocks,
          blockContentTypes,
          blockContentProperties,
          blockUITypes,
          blockUIProperties,
          shifu_id
        )
      },
      3000
    ),
    [saveCurrentBlocks]
  ) as (
    outline: string,
    blocks: Block[],
    blockContentTypes: Record<string, any>,
    blockContentProperties: Record<string, any>,
    blockUITypes: Record<string, any>,
    blockUIProperties: Record<string, any>,
    shifu_id: string
  ) => Promise<ApiResponse<SaveBlockListResult> | null>

  const addSiblingOutline = async (item: Outline, name = '') => {
    const id = 'new_chapter'
    const parent = findNode(item.parent_bid || '')
    const index = parent?.children?.findIndex(
      (child: any) => child.id === item.id
    )
    // insert item after index;
    parent.children?.splice(index + 1, 0, {
      id,
      parent_bid: parent.id,
      name: name,
      children: [],
      position: '',
      depth: (parent?.depth || 0) + 1
    })

    updateOuline(id, {
      parent_bid: parent.id,
      bid: id,
      id,
      name: name,
      children: [],
      position: '',
      depth: (parent?.depth || 0) + 1
    })

    setChapters([...chapters])

    setFocusId(id)
  }

  const createChapter = async (data: Outline) => {
    setIsSaving(true)
    setError(null)
    updateOutlineStatus(data.id, 'saving')
    const index = chapters.findIndex(child => child.id === data.id)

    try {
      if (data.id === 'new_chapter') {
        const newChapter = await api.createOutline({
          parent_bid: "",
          index: index,
          name: data.name,
          description: data.name,
          type: 'trial',
          system_prompt: '',
          is_hidden: false,
          shifu_id: currentShifu  ?.bid || ''
        })
        replaceOutline('new_chapter', {
          id: newChapter.bid,
          bid: newChapter.bid,
          name: newChapter.name,
          position: '',
          children: []
        })
        setFocusId('')
        setLastSaveTime(new Date())
      } else {
        await api.modifyOutline({
          outline_bid: data.id,
          index: index,
          description: data.name,
          name: data.name,
          shifu_id: currentShifu?.bid || ''
        })

        const currentChapter = chapters.find(chapter => chapter.id === data.id)

        replaceOutline(data.id, {
          id: data.id,
          bid: data.bid,
          name: data.name,
          position: '',
          children: currentChapter?.children || []
        })
        setFocusId('')
        setLastSaveTime(new Date())
      }
    } catch (error) {
      console.error(error)
      setError(
        data.id === 'new_chapter'
          ? 'Failed to create chapter'
          : 'Failed to modify chapter'
      )
      updateOutlineStatus(data.id, data.id === 'new_chapter' ? 'new' : 'edit')
      setFocusId(data.id)
    } finally {
      setIsSaving(false)
      setIsLoading(false)
    }
  }

  const createOutline = async (data: Outline) => {
    setIsSaving(true)
    setError(null)
    updateOutlineStatus(data.bid, 'saving')
    console.log('createOutline', data)

    const parent = findNode(data.parent_bid || '')
    const index = parent?.children?.findIndex(child => child.bid === data.bid) || 0

    try {
      if (data.bid === 'new_chapter') {
        const newUnit = await api.createOutline({
          parent_bid: data.parent_bid,
          index: index,
          name: data.name,
          description: data.name,
          type: 'trial',
          system_prompt: '',
          is_hidden: false,
          shifu_bid: currentShifu?.bid || ''
        })

        replaceOutline('new_chapter', {
          id: newUnit.bid,
          bid: newUnit.bid,
          name: newUnit.name,
          position: '',
          children: []
        })
        setFocusId('')
        setLastSaveTime(new Date())
      } else {
        await api.modifyOutline({
          outline_bid: data.id,
          index: index,
          description: data.name,
          name: data.name,
          shifu_bid: currentShifu?.bid || ''
        })
        replaceOutline(data.id, {
          id: data.id,
          bid: data.bid,
          name: data.name,
          position: data.position,
        })
        setFocusId('')
        setLastSaveTime(new Date())
      }
    } catch (error) {
      console.error(error)
      setError(
        data.id === 'new_chapter'
          ? 'Failed to create unit'
          : 'Failed to modify unit'
      )
      updateOutlineStatus(data.id, data.id === 'new_chapter' ? 'new' : 'edit')
      setFocusId(data.id)
    } finally {
      setIsSaving(false)
      setIsLoading(false)
    }
  }

  const createSiblingUnit = async (data: Outline) => {
    try {
      updateOutlineStatus(data.id, 'saving')
      setError(null)

      const parent = findNode(data.parent_bid || '')
      // get node index in children
      const index = parent.children.findIndex(child => child.id === data.id)

      const newUnit = await api.createOutline({
        parent_bid: data.parent_bid,
        index: index - 1,
        name: data.name,
        description: data.name,
        type: 'trial',
        system_prompt: '',
        is_hidden: false,
        shifu_id: currentShifu?.bid || ''
      })

      replaceOutline('new_chapter', {
        id: newUnit.bid,
        parent_bid: parent.bid,
        bid: newUnit.bid,
        name: newUnit.name,
        position: '',
        children: []
      })
    } catch (error) {
      console.error(error)
      setError('Failed to create chapter')
    } finally {
      setIsLoading(false)
    }
  }

  const updateOutlineStatus = (
    id: string,
    status: 'new' | 'edit' | 'saving'
  ) => {
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
    if (cataData['new_chapter']) {
      return
    }
    if (chapters?.find((child: any) => child.id === 'new_chapter')) {
      return
    }
    setChapters([...chapters, chapter])
    updateOuline(chapter.id, {
      ...chapter,
      status: 'new'
    })
    setFocusId(chapter.id)
  }
  const replaceOutline = async (id: string, outline: Outline) => {
    const node = findNode(id)
    console.log('replaceOutline', id, outline, node)
    node.id = outline.id
    node.name = outline.name
    node.position = outline.position
    node.parent_bid = outline.parent_bid
    node.bid = outline.bid
    if (outline.children && outline.children.length > 0) {
      node.children = outline.children
    }
    setChapters([...chapters])
    delete cataData[id]
    setCataData({
      ...cataData,
      [outline.id]: {
        ...outline,
        status: 'edit'
      }
    })
  }


  const setBlockContentPropertiesById = (
    id: string,
    properties: AIBlockProperties | SolidContentBlockProperties,
    reset: boolean = false
  ) => {
    if (reset) {
      setBlockContentProperties({
        ...blockContentProperties,
        [id]: properties
      })
      return
    }
    setBlockContentProperties({
      ...blockContentProperties,
      [id]: {
        ...blockContentProperties[id],
        ...properties
      }
    })
  }
  const setBlockContentTypesById = (id: string, type: string) => {
    setBlockContentTypes({
      ...blockContentTypes,
      [id]: type
    })
  }
  const setBlockUIPropertiesById = (
    id: string,
    properties: any,
    reset: boolean = false
  ) => {
    if (reset) {
      setBlockUIProperties({
        ...blockUIProperties,
        [id]: properties
      })
      return
    }
    setBlockUIProperties({
      ...blockUIProperties,
      [id]: {
        ...blockUIProperties[id],
        ...properties
      }
    })
  }
  const setBlockUITypesById = (id: string, type: string) => {
    setBlockUITypes({
      ...blockUITypes,
      [id]: type
    })
  }
  const setBlockContentStateById = (id: string, state: 'edit' | 'preview') => {
    setBlockContentState({
      ...blockContentState,
      [id]: state
    })
  }
  const updateChapterOrder = async (
    move_chapter_id: string,
    move_to_parent_id?: string,
    chapter_ids?: string[]
  ) => {
    setIsSaving(true)
    setError(null)
    try {
      await api.updateChapterOrder({
        move_chapter_id,
        move_to_parent_id,
        chapter_ids,
        shifu_id: currentShifu?.bid
      })
      setLastSaveTime(new Date())
    } catch (error) {
      console.error(error)
      setError('Failed to update chapter order')
    } finally {
      setIsSaving(false)
    }
  }
  const removeBlock = async (id: string) => {
    const list = blocks.filter(block => block.properties.block_id !== id)
    setBlocks(list)
    await saveCurrentBlocks(
      currentNode!.bid,
      list,
      blockContentTypes,
      blockContentProperties,
      blockUITypes,
      blockUIProperties,
      currentShifu?.bid || ''
    )
  }
  const loadModels = async () => {
    const list = await api.getModelList({})
    setModels(list)
  }

  const setBlockError = (blockId: string, error: string | null) => {
    setBlockErrors(prev => ({
      ...prev,
      [blockId]: error
    }))
  }

  const clearBlockErrors = () => {
    setBlockErrors({})
  }

  const reorderOutlineTree = async (outlines: ReorderOutlineItemDto[]) => {
    await api.reorderOutlineTree({
      shifu_bid: currentShifu?.bid || '',
      outlines
    })
  }
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
    blockContentTypes,
    blockUIProperties,
    blockUITypes,
    blockContentState,
    blockErrors,
    currentNode,
    profileItemDefinations,
    models,
    actions: {
      setFocusId,
      addChapter,
      setChapters,
      loadShifu,
      loadChapters,
      createChapter,
      setFocusValue,
      updateOuline,
      addSubOutline,
      addSiblingOutline,
      removeOutline,
      replaceOutline,
      createSiblingUnit,
      createOutline,
      loadBlocks,
      addBlock,
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
      setCurrentNode,
      loadModels,
      setBlockError,
      clearBlockErrors,
      reorderOutlineTree
    }
  }

  return <ShifuContext.Provider value={value}>{children}</ShifuContext.Provider>
}

export const useShifu = (): ShifuContextType => {
  const context = useContext(ShifuContext)
  if (context === undefined) {
    throw new Error('useShifu must be used within a ShifuProvider')
  }
  return context
}

/** inject variable to mc-editor */
'use client'
import React, { useState, useCallback } from 'react'
import { Edit, Plus, Trash2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Variable, EnumItem, DataType } from '@/components/cm-editor/type'

// TODO: test data
const testVariables = [
  {
    id: '1',
    name: '用户名',
    alias: '当前登录用户的名称',
    type: 'system',
    dataType: 'string'
  },
  {
    id: '2',
    name: '邮箱',
    alias: '用户邮箱地址',
    type: 'system',
    dataType: 'string'
  },
  {
    id: '3',
    name: '手机号',
    alias: '用户手机号码',
    type: 'system',
    dataType: 'string'
  },
  {
    id: '4',
    name: '状态',
    alias: '用户状态',
    type: 'custom',
    dataType: 'enum',
    enumItems: [
      { value: 'active', alias: '活跃' },
      { value: 'inactive', alias: '非活跃' }
    ]
  }
]

interface VariableInjectProps {
  onSelect?: (variable: Variable) => void
}

const VariableInject: React.FC<VariableInjectProps> = ({
  onSelect = () => {},
}) => {
  const [variables, setVariables] = useState<Variable[]>(
    testVariables as Variable[]
  )
  const [dialogOpen, setDialogOpen] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editingId, setEditingId] = useState<string>('')
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [newVariable, setNewVariable] = useState<Omit<Variable, 'id'>>({
    name: '',
    alias: '',
    type: 'custom',
    dataType: 'string',
    defaultValue: '',
    enumItems: []
  })
  const [newEnumItem, setNewEnumItem] = useState<EnumItem>({
    value: '',
    alias: ''
  })

  const handleAddVariable = useCallback((variable: Omit<Variable, 'id'>) => {
    const newId = `custom-${Date.now()}`
    setVariables(prev => [...prev, { ...variable, id: newId }])
  }, [])

  const handleUpdateVariable = useCallback(
    (id: string, variable: Omit<Variable, 'id'>) => {
      setVariables(prev =>
        prev.map(v => (v.id === id ? { ...variable, id } : v))
      )
    },
    []
  )

  const handleDeleteVariable = useCallback((id: string) => {
    setVariables(prev => prev.filter(v => v.id !== id))
  }, [])

  // 过滤变量
  const filteredVariables = variables.filter(
    variable =>
      variable.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      variable.alias.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const systemVariables = filteredVariables.filter(v => v.type === 'system')
  const customVariables = filteredVariables.filter(v => v.type === 'custom')

  const resetForm = () => {
    setNewVariable({
      name: '',
      alias: '',
      type: 'custom',
      dataType: 'string',
      defaultValue: '',
      enumItems: []
    })
    setNewEnumItem({ value: '', alias: '' })
    setIsEditing(false)
    setEditingId('')
  }

  const handleOpenDialog = (isEdit: boolean, variable?: Variable) => {
    if (isEdit && variable) {
      setIsEditing(true)
      setEditingId(variable.id)
      setNewVariable({
        name: variable.name,
        alias: variable.alias,
        type: variable.type,
        dataType: variable.dataType,
        defaultValue: variable.defaultValue || '',
        enumItems: variable.enumItems ? [...variable.enumItems] : []
      })
    } else {
      resetForm()
    }
    setDialogOpen(true)
  }

  const handleSaveVariable = () => {
    if (newVariable.name.trim()) {
      const variableToSave: Omit<Variable, 'id'> = {
        ...newVariable,
        enumItems:
          newVariable.dataType === 'enum' ? newVariable.enumItems : undefined,
        defaultValue:
          newVariable.dataType === 'string'
            ? newVariable.defaultValue
            : undefined
      }

      if (isEditing) {
        handleUpdateVariable(editingId, variableToSave)
      } else {
        handleAddVariable(variableToSave)
      }

      resetForm()
      setDialogOpen(false)
    }
  }

  const handleAddEnumItem = () => {
    if (newEnumItem.value.trim() && newEnumItem.alias.trim()) {
      setNewVariable({
        ...newVariable,
        enumItems: [...(newVariable.enumItems || []), { ...newEnumItem }]
      })
      setNewEnumItem({ value: '', alias: '' })
    }
  }

  const handleRemoveEnumItem = (index: number) => {
    const updatedEnumItems = [...(newVariable.enumItems || [])]
    updatedEnumItems.splice(index, 1)
    setNewVariable({
      ...newVariable,
      enumItems: updatedEnumItems
    })
  }

  return (
    <div className='space-y-4'>
      <div className='relative'>
        <Input
          placeholder='搜索变量...'
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          className='w-full'
        />
        {searchTerm && (
          <Button
            variant='ghost'
            size='icon'
            className='absolute right-2 top-1/2 -translate-y-1/2 h-6 w-6'
            onClick={() => setSearchTerm('')}
          >
            <X className='h-4 w-4' />
          </Button>
        )}
      </div>
      <ScrollArea className='h-[300px] rounded-md border'>
        <div className='p-4 space-y-4'>
          {systemVariables.length > 0 && (
            <div>
              <h4 className='mb-2 text-sm font-medium text-muted-foreground'>
                系统变量
              </h4>
              <div className='space-y-1'>
                {systemVariables.map(variable => (
                  <div
                    key={variable.id}
                    className='flex items-center justify-between p-2 rounded-md hover:bg-accent cursor-pointer'
                    onClick={() => onSelect(variable)}
                    onMouseEnter={() => setHoveredId(variable.id)}
                    onMouseLeave={() => setHoveredId(null)}
                  >
                    <div className='flex flex-col'>
                      <span>{variable.name}</span>
                      {variable.alias && (
                        <span className='text-xs text-muted-foreground'>
                          {variable.alias}
                        </span>
                      )}
                    </div>
                    <div className='flex items-center'>
                      <span className='text-xs text-muted-foreground mr-2'>
                        {variable.dataType === 'string' ? '字符串' : '枚举'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {customVariables.length > 0 && (
            <div>
              <h4 className='mb-2 text-sm font-medium text-muted-foreground'>
                自定义变量
              </h4>
              <div className='space-y-1'>
                {customVariables.map(variable => (
                  <div
                    key={variable.id}
                    className='flex items-center justify-between p-2 rounded-md hover:bg-accent cursor-pointer group'
                    onClick={() => onSelect(variable)}
                    onMouseEnter={() => setHoveredId(variable.id)}
                    onMouseLeave={() => setHoveredId(null)}
                  >
                    <div className='flex flex-col'>
                      <div className='flex items-center'>
                        <span>{variable.name}</span>
                        {hoveredId === variable.id &&
                          variable.dataType === 'string' &&
                          variable.defaultValue && (
                            <span className='text-xs text-muted-foreground ml-2 bg-muted px-1.5 py-0.5 rounded'>
                              默认值: {variable.defaultValue}
                            </span>
                          )}
                      </div>
                      {variable.alias && (
                        <span className='text-xs text-muted-foreground'>
                          {variable.alias}
                        </span>
                      )}
                    </div>
                    <div className='flex items-center'>
                      <span className='text-xs text-muted-foreground mr-2'>
                        {variable.dataType === 'string' ? '字符串' : '枚举'}
                      </span>

                      {hoveredId === variable.id ? (
                        <div
                          className='flex'
                          onClick={e => e.stopPropagation()}
                        >
                          <Button
                            variant='ghost'
                            size='icon'
                            className='h-6 w-6'
                            onClick={e => {
                              e.stopPropagation()
                              handleOpenDialog(true, variable)
                            }}
                          >
                            <Edit className='h-4 w-4' />
                          </Button>
                          <Button
                            variant='ghost'
                            size='icon'
                            className='h-6 w-6'
                            onClick={e => {
                              e.stopPropagation()
                              handleDeleteVariable(variable.id)
                            }}
                          >
                            <Trash2 className='h-4 w-4' />
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {filteredVariables.length === 0 && (
            <div className='py-6 text-center text-muted-foreground'>
              未找到变量
            </div>
          )}
        </div>
      </ScrollArea>

      <Button
        variant='outline'
        className='w-full'
        onClick={() => handleOpenDialog(false)}
      >
        <Plus className='mr-2 h-4 w-4' />
        添加新变量
      </Button>

      <Dialog
        open={dialogOpen}
        onOpenChange={open => {
          if (!open) resetForm()
          setDialogOpen(open)
        }}
      >
        <DialogContent className='sm:max-w-[500px]'>
          <DialogHeader>
            <DialogTitle>{isEditing ? '编辑变量' : '添加新变量'}</DialogTitle>
            <DialogDescription>
              {isEditing ? '修改现有变量的属性。' : '创建一个新的自定义变量。'}
            </DialogDescription>
          </DialogHeader>
          <div className='grid gap-4 py-4'>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='name' className='text-right'>
                变量名
              </Label>
              <Input
                id='name'
                value={newVariable.name}
                onChange={e =>
                  setNewVariable({ ...newVariable, name: e.target.value })
                }
                className='col-span-3'
              />
            </div>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label htmlFor='alias' className='text-right'>
                别名
              </Label>
              <Input
                id='alias'
                value={newVariable.alias}
                onChange={e =>
                  setNewVariable({ ...newVariable, alias: e.target.value })
                }
                className='col-span-3'
                placeholder='可选'
              />
            </div>
            <div className='grid grid-cols-4 items-center gap-4'>
              <Label className='text-right'>数据类型</Label>
              <div className='col-span-3'>
                <RadioGroup
                  value={newVariable.dataType}
                  onValueChange={(value: DataType) =>
                    setNewVariable({ ...newVariable, dataType: value })
                  }
                  className='flex flex-row space-x-4'
                >
                  <div className='flex items-center space-x-2'>
                    <RadioGroupItem value='string' id='string' />
                    <Label htmlFor='string'>字符串</Label>
                  </div>
                  <div className='flex items-center space-x-2'>
                    <RadioGroupItem value='enum' id='enum' />
                    <Label htmlFor='enum'>枚举</Label>
                  </div>
                </RadioGroup>
              </div>
            </div>

            {newVariable.dataType === 'string' && (
              <div className='grid grid-cols-4 items-center gap-4'>
                <Label htmlFor='defaultValue' className='text-right'>
                  默认值
                </Label>
                <Input
                  id='defaultValue'
                  value={newVariable.defaultValue || ''}
                  onChange={e =>
                    setNewVariable({
                      ...newVariable,
                      defaultValue: e.target.value
                    })
                  }
                  className='col-span-3'
                  placeholder='可选'
                />
              </div>
            )}

            {newVariable.dataType === 'enum' && (
              <>
                <div className='grid grid-cols-4 gap-4'>
                  <div className='col-span-4'>
                    <Label className='mb-2 block'>枚举项</Label>
                    {(newVariable.enumItems || []).length > 0 && (
                      <div className='mb-3 rounded-md border'>
                        <div className='grid grid-cols-12 border-b bg-muted px-3 py-2 text-sm font-medium'>
                          <div className='col-span-5'>枚举值</div>
                          <div className='col-span-5'>别名</div>
                          <div className='col-span-2 text-right'>操作</div>
                        </div>
                        <div className='divide-y'>
                          {(newVariable.enumItems || []).map((item, index) => (
                            <div
                              key={index}
                              className='grid grid-cols-12 items-center px-3 py-2'
                            >
                              <div className='col-span-5 truncate'>
                                {item.value}
                              </div>
                              <div className='col-span-5 truncate'>
                                {item.alias}
                              </div>
                              <div className='col-span-2 text-right'>
                                <Button
                                  variant='ghost'
                                  size='icon'
                                  className='h-7 w-7'
                                  onClick={() => handleRemoveEnumItem(index)}
                                >
                                  <X className='h-4 w-4' />
                                </Button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className='grid grid-cols-12 gap-2'>
                      <Input
                        placeholder='枚举值'
                        value={newEnumItem.value}
                        onChange={e =>
                          setNewEnumItem({
                            ...newEnumItem,
                            value: e.target.value
                          })
                        }
                        className='col-span-5'
                      />
                      <Input
                        placeholder='别名'
                        value={newEnumItem.alias}
                        onChange={e =>
                          setNewEnumItem({
                            ...newEnumItem,
                            alias: e.target.value
                          })
                        }
                        className='col-span-5'
                      />
                      <Button
                        onClick={handleAddEnumItem}
                        className='col-span-2'
                        disabled={
                          !newEnumItem.value.trim() || !newEnumItem.alias.trim()
                        }
                      >
                        添加
                      </Button>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
          <DialogFooter>
            <Button
              variant='outline'
              onClick={() => {
                resetForm()
                setDialogOpen(false)
              }}
            >
              取消
            </Button>
            <Button
              onClick={handleSaveVariable}
              disabled={
                !newVariable.name.trim() ||
                (newVariable.dataType === 'enum' &&
                  (newVariable.enumItems || []).length === 0)
              }
            >
              {isEditing ? '保存' : '添加'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
export default VariableInject

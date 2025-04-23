enum SelectedOption {
  Video = 'video',
  Image = 'Image',
  Variable = 'Variable',
  Empty = ''
}
interface IEditorContext {
  selectedOption: SelectedOption
  setSelectedOption: (selectedOption: SelectedOption) => void
  dialogOpen: boolean
  setDialogOpen: (dialogOpen:boolean) => void
  profileList?: string[],
  setProfileList?: (profiles: string[]) => void
}


type VariableType = 'system' | 'custom'
type DataType = 'string' | 'enum'

interface EnumItem {
  value: string
  alias: string
}

interface Variable {
  id: string
  name: string
  alias: string
  type: VariableType
  dataType: DataType
  defaultValue?: string
  enumItems?: EnumItem[]
}


export { SelectedOption }
export type { IEditorContext, Variable, EnumItem, VariableType, DataType }

import { createContext } from 'react'
import {IEditorContext, SelectedOption} from './type'

const EditorContext = createContext<IEditorContext>({
  selectedOption: SelectedOption.Empty,
  setSelectedOption: () => {},
  dialogOpen: false,
  setDialogOpen: () => {}
})
export default EditorContext;

enum SelectedOption {
  Video = 'video',
  Image = 'Image',
  Profile = 'Profile',
  Empty = '',
}
interface IEditorContext {
  selectedOption: SelectedOption;
  setSelectedOption: (selectedOption: SelectedOption) => void;
  dialogOpen: boolean;
  setDialogOpen: (dialogOpen: boolean) => void;
  profileList?: string[];
  setProfileList?: (profiles: string[]) => void;
}

export { SelectedOption };
export type { IEditorContext };

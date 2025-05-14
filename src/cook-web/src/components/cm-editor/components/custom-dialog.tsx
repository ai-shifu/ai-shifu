import React, { useContext } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import EditorContext from '../editor-context'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'

type CustomDialogProps = {
  children?: React.ReactNode
}

const CustomDialog: React.FC<CustomDialogProps> = ({ children }) => {
  const { t } = useTranslation()
  const { dialogOpen, setDialogOpen } = useContext(EditorContext)
  return (
    <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen} modal>
      <Dialog.Portal>
        <Dialog.Overlay
          className='fixed inset-0 bg-black/50'
          onClick={e => {
            e.preventDefault()
            e.stopPropagation()
          }}
        />
        <Dialog.Content
          className='fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg p-6 shadow-lg min-w-[400px]'
          onPointerDownOutside={e => {
            e.preventDefault()
          }}
          onInteractOutside={e => {
            e.preventDefault()
          }}
        >
          <Dialog.Title className='font-medium mb-4'>
            {t('common.please-set')}
          </Dialog.Title>
          <div className='space-y-4'>{children}</div>
          <Dialog.Close
            className='absolute top-4 right-4 text-gray-500 hover:text-gray-700'
            onClick={() => setDialogOpen(false)}
          >
            <X className='h-4 w-4' />
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export default CustomDialog

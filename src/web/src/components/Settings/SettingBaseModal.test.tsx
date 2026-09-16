import { act } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import { DialogDescription, DialogTitle } from '@/components/ui/Dialog';
import SettingBaseModal from './SettingBaseModal';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('SettingBaseModal outside dismissal', () => {
  it.each(['Escape', 'close icon'])(
    'inherits outside-click protection and still closes through %s',
    async closeMethod => {
      const onClose = jest.fn();

      render(
        <SettingBaseModal
          open
          onOk={jest.fn()}
          onClose={onClose}
          title='Settings'
          header={(_, title) => <DialogTitle>{title}</DialogTitle>}
        >
          <DialogDescription>Settings description</DialogDescription>
        </SettingBaseModal>,
      );

      // Radix registers its outside pointer listener on the next task.
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 0));
      });
      fireEvent.pointerDown(document.body, { pointerType: 'mouse' });
      fireEvent.click(document.body);

      expect(onClose).not.toHaveBeenCalled();

      if (closeMethod === 'Escape') {
        fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
      } else {
        fireEvent.click(
          screen.getByRole('button', { name: 'component.header.close' }),
        );
      }
      expect(onClose).toHaveBeenCalledTimes(1);
    },
  );
});

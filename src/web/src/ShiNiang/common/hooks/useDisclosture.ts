import { useCallback } from 'react';
import { useState } from 'react';

export const useDisclosture = ({ initOpen = false } = {}) => {
  const [open, setOpen] = useState(initOpen);

  const onOpen = useCallback(() => {
    setOpen(true);
  }, []);

  const onClose = useCallback(() => {
    setOpen(false);
  }, []);

  const onToggle = useCallback(() => {
    setOpen((prev) => !prev);
  }, []);

  return {
    open,
    onOpen,
    onClose,
    onToggle,
  };
};

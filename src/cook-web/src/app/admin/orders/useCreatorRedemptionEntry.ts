'use client';

import { useCallback, useState } from 'react';

export const useCreatorRedemptionEntry = ({
  onSuccess,
}: {
  onSuccess: () => void;
}) => {
  const [redemptionOpen, setRedemptionOpen] = useState(false);
  const [redemptionReloadKey, setRedemptionReloadKey] = useState(0);

  const openRedemptionDialog = useCallback(() => {
    setRedemptionOpen(true);
  }, []);

  const handleRedemptionOpenChange = useCallback((open: boolean) => {
    setRedemptionOpen(open);
  }, []);

  const handleRedemptionSuccess = useCallback(() => {
    setRedemptionReloadKey(current => current + 1);
    onSuccess();
  }, [onSuccess]);

  return {
    handleRedemptionOpenChange,
    handleRedemptionSuccess,
    openRedemptionDialog,
    redemptionOpen,
    redemptionReloadKey,
  };
};

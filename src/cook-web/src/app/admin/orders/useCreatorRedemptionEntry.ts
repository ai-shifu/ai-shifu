'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export const useCreatorRedemptionEntry = ({
  onSuccess,
}: {
  onSuccess: () => void;
}) => {
  const [redemptionOpen, setRedemptionOpen] = useState(false);
  const [redemptionReloadKey, setRedemptionReloadKey] = useState(0);
  const onSuccessRef = useRef(onSuccess);

  useEffect(() => {
    onSuccessRef.current = onSuccess;
  }, [onSuccess]);

  const openRedemptionDialog = useCallback(() => {
    setRedemptionOpen(true);
  }, []);

  const handleRedemptionOpenChange = useCallback((open: boolean) => {
    setRedemptionOpen(open);
  }, []);

  const handleRedemptionSuccess = useCallback(() => {
    setRedemptionReloadKey(current => current + 1);
    onSuccessRef.current();
  }, []);

  return {
    handleRedemptionOpenChange,
    handleRedemptionSuccess,
    openRedemptionDialog,
    redemptionOpen,
    redemptionReloadKey,
  };
};

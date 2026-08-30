'use client';

import React from 'react';
import { attachBrowserHistoryGuardBridge } from '@/lib/browserHistoryGuard';

const BrowserHistoryGuardBridge = () => {
  React.useLayoutEffect(() => attachBrowserHistoryGuardBridge(), []);
  return null;
};

export default BrowserHistoryGuardBridge;

'use client';

import { useEffect } from 'react';
import { installReactDomNodeGuard } from '@/lib/domReconcilerGuard';

// Install as early as the client bundle is evaluated — before React commits the
// lesson preview tree that browser translation can crash. The installer is a
// no-op on the server and idempotent, so the module-top-level call is SSR-safe.
installReactDomNodeGuard();

const DomReconcilerGuard = () => {
  // Redundant call covers fast-refresh remounts; idempotent, so harmless.
  useEffect(() => {
    installReactDomNodeGuard();
  }, []);

  return null;
};

export default DomReconcilerGuard;

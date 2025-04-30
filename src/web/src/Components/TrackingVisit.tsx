import { memo } from 'react';
import { useTracking, EVENT_NAMES } from 'common/hooks/useTracking';
import { useState } from 'react';

export const TrackingVisit = () => {
  const [ok, setOk] = useState(false);
  const { trackEvent } = useTracking();

  if (!ok) {
    trackEvent(EVENT_NAMES.VISIT, {});
    setOk(true);
  }
};

export default memo(TrackingVisit);

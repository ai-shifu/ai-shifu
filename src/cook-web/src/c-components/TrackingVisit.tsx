import { memo, useState } from "react"
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';

export const TrackingVisit = () => {
  const [ok, setOk] = useState(false);
  const { trackEvent } = useTracking();

  if (!ok) {
    trackEvent(EVENT_NAMES.VISIT, {});
    setOk(true);
  }
}

export default memo(TrackingVisit);

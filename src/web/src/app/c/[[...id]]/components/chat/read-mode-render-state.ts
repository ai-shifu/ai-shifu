export const shouldHideReadModeContentForLoading = ({
  isLoading,
  hasReadModeItems,
  shouldShowReadModeStreamingDots,
}: {
  isLoading: boolean;
  hasReadModeItems: boolean;
  shouldShowReadModeStreamingDots: boolean;
}) => isLoading && !hasReadModeItems && !shouldShowReadModeStreamingDots;

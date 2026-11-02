export const getDocumentFullscreenElement = () => {
  if (typeof document === 'undefined') {
    return null;
  }

  return (
    document.fullscreenElement ??
    (
      document as Document & {
        webkitFullscreenElement?: Element | null;
      }
    ).webkitFullscreenElement ??
    null
  );
};

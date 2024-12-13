export const parseUrlParams = () => {
  return getQueryParams(window.location.href);
};

export function getQueryParams(url) {
  const params = {};
  const queryString = url.split('?')[1];
  if (queryString) {
    queryString.split('&').forEach(param => {
      const [key, value] = param.split('=');
      params[key] = decodeURIComponent(value);
    });
  }
  return params;
}

// remove some query params from url
export const removeParamFromUrl = (url, paramsToRemove) => {
  const urlObj = new URL(url);
  const searchParams = urlObj.searchParams;

  for (const paramToRemove of paramsToRemove) {
    searchParams.delete(paramToRemove);
  }

  return urlObj.toString();
}

import http, { RequestConfig, StreamCallback, StreamRequestConfig } from './request';
const apiPrefix = '/api';

const objectToQueryString = (obj: any) => {
    const params = new URLSearchParams();
    for (const key in obj) {
        params.append(key, obj[key]);
    }
    return params.toString();
};
export const gen = (option: string) => {
    let url = option;
    let method = 'GET';

    const paramsArray = option.split(' ');
    if (paramsArray.length === 2) {
        method = paramsArray[0];
        url = paramsArray[1];
    }

    if (!url.startsWith('http')) {
        url = apiPrefix + url;
    }

    return function (params: { [x: string]: any }, config: RequestConfig | StreamRequestConfig = {}, callback?: StreamCallback) {
        let tarUrl = url;
        let body;

        const urlParams = url.match(/\{([^}]+)\}/g);
        const urlParamsMap = { ...params };
        if (urlParams) {
            urlParams.forEach(param => {
                const key = param.replace('{', '').replace('}', '');
                tarUrl = tarUrl.replace(param, urlParamsMap[key] || param);
                delete urlParamsMap[key];
            });
        }

        if (method === 'GET') {
            if (urlParamsMap && Object.keys(urlParamsMap).length > 0) {
                const queryString = objectToQueryString(urlParamsMap);
                tarUrl = `${tarUrl}?${queryString}`;
            }

        } else {
            if (urlParamsMap && Object.keys(urlParamsMap).length > 0) {
                body = JSON.stringify(urlParamsMap);
            }
        }

        if (method === 'STREAM') {
            return http.interceptFetchByStream(tarUrl, {
                ...config,
                body,
                method,
            }, callback);
        }
        if (method === 'STREAMLINE') {
            return http.interceptFetchByStreamLine(tarUrl, {
                ...config,
                body,
                method,
            }, callback);
        }
        if (method === 'PROXY') {
            return http.fetch(tarUrl, {
                ...config,
                body,
                method,
            });
        }
        return http.interceptFetch(tarUrl, {
            ...config,
            body,
            method,
        });
    };
};

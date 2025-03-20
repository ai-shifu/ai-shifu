/* eslint-disable @typescript-eslint/no-explicit-any */
import http, { RequestConfig, StreamCallback, StreamRequestConfig } from './request';
const apiPrefix = '/api';

const objectToQueryString = (obj: any) => {
    const params = new URLSearchParams();
    for (const key in obj) {
        // if (obj.hasOwnProperty(key)) {
        params.append(key, obj[key]);
        // }
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
        if (method === 'GET') {
            if (params) {
                const queryString = objectToQueryString(params);
                tarUrl = `${url}?${queryString}`;
            }

        } else {
            if (params) {
                body = JSON.stringify(params);
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

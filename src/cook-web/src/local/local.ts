/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable @typescript-eslint/no-explicit-any */

const USER_TOKEN = 'user_token';

export const setLocalStore = (key: string, value: any = {}) => {
    let localStore: any = window.localStorage;
    if (!localStore) {
        localStore = window.sessionStorage;
    }

    if (value == null || typeof value === 'undefined' || value == '') {
        localStore?.removeItem(key);
    } else {
        localStore?.setItem(key, JSON.stringify(value));
    }
};


export const getLocalStore = (key: string) => {
    let localStore: any = window.localStorage;
    if (!localStore) {
        localStore = window.sessionStorage;
    }

    const value = localStore?.getItem(key);
    try {
        return value ? JSON.parse(value) : undefined;
    } catch (e) {
        return undefined;
    }
};

export const getToken = async () => {
    return getLocalStore(USER_TOKEN) || '';
};

export const setToken = async (token: string) => {
    return setLocalStore(USER_TOKEN, token);
};

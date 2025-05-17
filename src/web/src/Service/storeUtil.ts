import store from 'store';

const TOKEN_KEY = 'token';
const USERINFO_KEY = 'userinfo';
const TOKEN_FAKED_KEY = 'token_faked';

const createStore = <T>(key: string) => {
  return {
    get: (): T | undefined => {
      return store.get(key);
    },
    set: (v: T): void => {
      store.set(key, v);
    },
    remove: (): void => {
      store.remove(key);
    }
  };
};

const createBoolStore = (key: string) => {
  return {
    get: (): boolean => {
      return !!parseInt(store.get(key));
    },
    set: (v: boolean): void => {
      const val = v ? 1 : 0;
      store.set(key, val);
    },
    remove: (): void => {
      store.remove(key);
    }
  };
};

export const tokenStore = createStore(TOKEN_KEY);
export const userInfoStore = createStore(USERINFO_KEY);
const tokenFakedStore = createBoolStore(TOKEN_FAKED_KEY);

export const tokenTool = {
  get: (): { token: string | undefined; faked: boolean } => ({
    token: tokenStore.get(),
    faked: tokenFakedStore.get(),
  }),
  set: ({ token, faked }: { token: string; faked: boolean }): void => {
    tokenStore.set(token);
    tokenFakedStore.set(faked);
  },
  remove: (): void => {
    tokenStore.remove();
    tokenFakedStore.remove();
  }
};

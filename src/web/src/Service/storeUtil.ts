import store from 'store';

const TOKEN_KEY = 'token';
const USERINFO_KEY = 'userinfo';
const TOKEN_FAKED_KEY = 'token_faked';

const createStore = (key) => {
  return {
    get: () => {
      return store.get(key);
    },
    set: (v) => {
      store.set(key, v);
    },
    remove: () => {
      store.remove(key);
    },
  };
};

const createBoolStore = (key) => {
  return {
    get: () => {
      return !!parseInt(store.get(key));
    },
    set: (v) => {
      const val = v ? 1 : 0;
      store.set(key, val);
    },
    remove: () => {
      store.remove(key);
    },
  };
};

export const tokenStore = createStore(TOKEN_KEY);
export const userInfoStore = createStore(USERINFO_KEY);
const tokenFakedStore = createBoolStore(TOKEN_FAKED_KEY);

export const tokenTool = {
  get: () => ({
    token: tokenStore.get(),
    faked: tokenFakedStore.get(),
  }),
  set: ({ token, faked }) => {
    tokenStore.set(token);
    tokenFakedStore.set(faked);
  },
  remove: () => {
    tokenStore.remove();
    tokenFakedStore.remove();
  },
};

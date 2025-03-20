import { gen } from '@/lib/api';
import api from './api';

export type IAPIKeys = keyof typeof api;
export type IAPIFunction = {
    [_x in IAPIKeys]: ReturnType<typeof gen>;
};

const APIFunction = {} as IAPIFunction;
for (const key in api) {
    APIFunction[key as IAPIKeys] = gen(api[key as IAPIKeys]);
}

export default APIFunction;

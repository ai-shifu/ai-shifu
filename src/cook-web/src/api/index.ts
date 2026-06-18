import { gen } from '@/lib/api';
import http, { RequestConfig } from '@/lib/request';
import api from './api';

export type IAPIKeys = keyof typeof api;
export type IAPIFunction = {
  [_x in IAPIKeys]: ReturnType<typeof gen>;
} & {
  submitMinimaxTtsVoiceClone: (
    formData: FormData,
    config?: RequestConfig,
  ) => Promise<unknown>;
};

const APIFunction = {} as IAPIFunction;
for (const key in api) {
  APIFunction[key as IAPIKeys] = gen(api[key as IAPIKeys]);
}

APIFunction.submitMinimaxTtsVoiceClone = (
  formData: FormData,
  config: RequestConfig = {},
) => http.post('/api/shifu/tts/minimax/voices/clone', formData, config);

export default APIFunction;

import { SSE } from 'sse.js';
import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from "axios";
// import { message } from "antd";
import { tokenTool } from "./storeUtil";
import { v4 } from "uuid";
import { useTranslation } from "react-i18next";
import { getStringEnv } from "@/c-utils/envUtils";
import { ApiResponse } from "@/c-types";
/**
 *
 * @param {*} token
 * @param {*} chatId
 * @param {*} text
 * @param {*} onMessage
 * @returns
 */
export const SendMsg = (
  token: string,
  chatId: string,
  text: string,
  onMessage?: (response: any) => void
): SSE => {
  var source = new SSE(getStringEnv('baseURL')+"/chat/chat-assistant?token="+token, {
    headers: { "Content-Type": "application/json" },
    payload: JSON.stringify({
      token: token,
      msg: text,
      chat_id: chatId,
    }),

  });
  source.addEventListener('message', (event: MessageEvent) => {
    try {
      var response = JSON.parse(event.data);
      if (onMessage) {
        onMessage(response);
      }
    } catch (e) {
      console.error(e);
    }
  });

  source.addEventListener('error', (event: Event) => {
    console.error(event);
  });
  source.stream();
  return source;
};


/**
 * @description 创建 axios 实例
 * @type {*}
 * */
const axiosrequest: AxiosInstance = axios.create({
  // baseURL: getStringEnv('baseURL'),
  withCredentials: false, // 跨域请求时发送 cookies
  headers: {"Content-Type":"application/json"}
});

// 创建请求拦截器
axiosrequest.interceptors.request.use(async(config: any)=>{
  config.baseURL = getStringEnv('baseURL');
  config.headers.token = tokenTool.get().token;
  config.headers["X-Request-ID"] = v4().replace(/-/g, '');
  return config;
});

// 创建响应拦截器
axiosrequest.interceptors.response.use(
  (response: any) => {
    if(response.data.code !== 0) {
      if (![1001].includes(response.data.code)) {
        // TODO: FIXME
        // message.error({content:response.data.message});
      }
      const apiError = new CustomEvent("apiError", {detail:response.data, bubbles:true,});
      document.dispatchEvent(apiError);
      return Promise.reject(response.data);
    }
    return response.data;
  }, (error: any) => {
    const apiError = new CustomEvent("apiError", {detail:error});
    document.dispatchEvent(apiError);
    // TODO: FIXME
    // const { t } = useTranslation();
    // message.error(t("common.networkError"));
    return Promise.reject(error);
  });

export default axiosrequest;

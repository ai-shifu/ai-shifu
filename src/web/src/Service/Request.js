import { SSE } from "sse.js";
import axios from "axios";
import { message } from "antd";
import { tokenStore } from "./storeUtil.js";
/**
 * 
 * @param {*} token 
 * @param {*} chatId 
 * @param {*} text 
 * @param {*} onMessage 
 * @returns 
 */
export const SendMsg = (token, chatId, text, onMessage) => {
  var source = new SSE(process.env.REACT_APP_BASEURL+"/chat/chat-assistant?token="+token, {
    headers: { "Content-Type": "application/json" },
    payload: JSON.stringify({
      token: token,
      msg: text,
      chat_id: chatId,
    }),
    
  });
  source.onmessage = (event) => {
    try {

      var response =JSON.parse (event.data)
      console.log("response", response,new Date());
      if (onMessage) {
        onMessage(response);
      }
    } catch (e) {
      console.log("error", e);
    }
  };
  source.onerror = (event) => {
    console.log("连接错误");
    console.log(event);
    // this.searchBoll = true;
  };
  source.onclose = (event) => {
    console.log("会话完成断开连接");
    // this.searchBoll = true;
    console.log(event);
  };
  source.stream();
  return source;
}


console.log('api base url: ', process.env.REACT_APP_BASEURL);

/**
 * @description 创建 axios 实例 
 * @type {*} 
 * */
const axiosrequest = axios.create({
  baseURL:process.env.REACT_APP_BASEURL,
  withCredentials: false, // 跨域请求时发送 cookies
  headers: {"Content-Type":"application/json"}
});

// 创建请求拦截器
axiosrequest.interceptors.request.use(async(config)=>{
  config.headers.token = tokenStore.get();
  return config;
})

// 创建响应拦截器
axiosrequest.interceptors.response.use(
  response => {
    if(response.data.code !== 0) {
      if (![1001].includes(response.data.code)) {
        message.error({content:response.data.message});
      }
      const apiError = new CustomEvent("apiError", {detail:response.data, bubbles:true,});
      document.dispatchEvent(apiError);
      return Promise.reject(response.data);
    }
    return response.data;
  },error => {
    const apiError = new CustomEvent("apiError", {detail:error});
    document.dispatchEvent(apiError);
    message.error("无法连接到服务器请检查网络设置");
    return Promise.reject(error);
  })

export default axiosrequest;

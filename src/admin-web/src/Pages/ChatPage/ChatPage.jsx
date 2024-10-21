import { Row, Col } from "antd";
import ChatList from "./ChatList";
import { useState } from "react";
import { UploadEvent } from "../../Api/UploadEvent";
import ChatComponents from "./ChatComponents";
import { useRef } from "react";
import "./ChatPage.css";
import {testOrder} from "../../Api/order";
const ChatPage = () => {
  UploadEvent("ChatPage", { page: "chatPage" });
  const chatComponents = useRef(null);
  const chatList = useRef(null);
  const onClickListItem = (chatInfo) => {
    // UploadEvent("view_chatInfo", { page: "chatPage" });

  };

  const onTitleUpdate = (chatId, chatTitle, created) => {
    console.log(chatId, chatTitle, created);
    chatList.current.onTitleUpdate(chatId, chatTitle, created);
  };
  const onClickMenuItem = (lessonInfo) => {
    if(lessonInfo && chatComponents.current){
      console.log('onClickMenuItem',lessonInfo)
      chatComponents.current.switchLesson(lessonInfo)
    }
  };

  const lessonStatusUpdate = (lessonUpdate)=>{
    console.debug('lessonupdate',lessonUpdate)
    chatList.current.updateLessonAttendInfo(lessonUpdate)
  }

  const onOrderBy = (orderBy) => {


    console.log("onOrderBy", orderBy);
    testOrder(orderBy).then((res) => {
      console.log("res", res)

      chatList.current.updateLessonList()
    })

  };
  return (
    <div className="chat-page full-height">
      <ChatList
        onClickListItem={onClickListItem}
        onClickMenuItem={onClickMenuItem}

        ref={chatList}
      ></ChatList>
      <ChatComponents
        className="chat-components"
        ref={chatComponents}
        onTitleUpdate={onTitleUpdate}
        lessonStatusUpdate = {lessonStatusUpdate}
        orderBuy={onOrderBy}
      />
    </div>
  );
};

export default ChatPage;

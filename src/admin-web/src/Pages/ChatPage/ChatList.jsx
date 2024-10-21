import { List, Skeleton } from "antd";
import "./ChatList.css";
import { Input, Button } from "antd";
import InfiniteScroll from "react-infinite-scroll-component";
import { createFromIconfontCN, PlusCircleOutlined } from "@ant-design/icons";
import { Dropdown } from "antd";
import { useState, forwardRef, useImperativeHandle, useEffect } from "react";
import { Empty } from "antd";
import create from "@ant-design/icons/lib/components/IconFont";
import { getLessonTree } from "../../Api/lesson";


import { Menu ,Badge} from 'antd';
import { MailOutlined, AppstoreOutlined, SettingOutlined } from '@ant-design/icons';
import { CheckCircleOutlined, PlayCircleOutlined,LockOutlined } from '@ant-design/icons';
import { Get } from "../../Api/lesson";

const { SubMenu } = Menu;




/**
 * @description 文档列表组件
 * @param {*} onClickListItem - 事件 点击列表中某一行的的方法
 * @returns
 */
const ChatList = forwardRef(
  ({ onClickListItem, onClickMenuItem }, ref) => {
    const [selectedSortOrder, setSelectedSortOrder] = useState();
    const [loading, setLoading] = useState();
    const [data, setData] = useState([]);
    const [lessonData,setLessonData] = useState([])
    const [courseId,setCourseId]=useState("")
    const params = {};
    const dataLength = 100;
    const onSearch = (chat_title) => {
      params.chat_title = chat_title;
      queryAllChatsList();
    };

    const onTitleUpdate = (chatId, chatTitle, created) => {
      if (data.length > 0) {
        const newData = data.map((item) => {
          if (item.chat_id === chatId) {
            item.chat_title += chatTitle;
          }
          return item;
        });
        if (data.filter((item) => item.chat_id === chatId) == 0) {
          newData.unshift({
            chat_id: chatId,
            chat_title: chatTitle,
            created: created,
          });
        }
        setData(newData);
      }
    };

    useImperativeHandle(ref, () => ({
      onTitleUpdate: (chatId, chatTitle, created) => {
        onTitleUpdate(chatId, chatTitle, created);
      },
      queryAllChatsList: () => {
        queryAllChatsList({ chat_title: "" });
      },
      updateLessonAttendInfo: (updateAttendInfo)=>{
        console.log('udpate attend info',updateAttendInfo)
        if  (lessonData){
          for( let i in lessonData){
            if(lessonData[i].lesson_id === updateAttendInfo.lesson_id){
              lessonData[i].status = updateAttendInfo.status
            }
            for(let c in lessonData[i].children){
              if(lessonData[i].children[c].lesson_id === updateAttendInfo.lesson_id){
              lessonData[i].children[c].status = updateAttendInfo.status
              }
            }
          }
          const newLessonData = lessonData.map(l=>l)
          setLessonData(newLessonData)
        }
      },
      updateLessonList:()=>{
        queryAllChatsList()
      }
    }));

    const queryAllChatsList = () => {
      getLessonTree().then((res) => {
        setLessonData(res.data.lessons);
        setCourseId(res.data.course_id)
      })
    };

    useState(() => {
      setLoading(true);
      queryAllChatsList();
    }, []);
    useEffect(()=>{
      console.log('update lesson',lessonData)
    },[lessonData])

    const clickMenuItem=(e,lessonInfo)=>{

      if(onClickMenuItem){
      onClickMenuItem({...lessonInfo, course_id:courseId});
      }
    }
    const getIcon = (sender)=>{
      let icon =   <CheckCircleOutlined style={{ color: 'green', float: 'right' }} />
      let status= sender.datasource ?  sender.datasource.status : sender.status;
      switch(status){
        case "未开始":
          icon = <PlayCircleOutlined style={{ color: 'green', float: 'right' }} />
          break;
        case "可学习":
            icon = <PlayCircleOutlined style={{ color: 'green', float: 'right' }} />
            break;
        case "进行中":
          icon = <PlayCircleOutlined style={{ color: 'green', float: 'right' }} />
          break;
        case "已完成":
          icon = <CheckCircleOutlined style={{ color: 'green', float: 'right' }} />
          break;
        case "未解锁":
            icon = <LockOutlined style={{ color: 'green', float: 'right' }} />
            break;

        default:
          icon = <LockOutlined style={{ color: 'green', float: 'right' }} />
          break;
      }
      return icon
    }


    return (
      <div id="chat_list_container" className="chat_list_container">
      <Menu
        mode="inline"
        expandIcon={getIcon}

      >
        {
          lessonData.map((item,index)=>{
            return <SubMenu key={index}  title={item.lesson_name } datasource={item}  >
              {
                item.children.map((chapter,index)=>{
                  return <Menu.Item key={chapter.lesson_no} datasource={chapter} onClick={(e)=>clickMenuItem(e,chapter)}  >
                    {chapter.lesson_name}
                  { getIcon(chapter)}
                    </Menu.Item>
                })
              }
            </SubMenu>
          })
        }

      </Menu>


        </div>

    );
  }
);

export default ChatList;

import MainLayout from "../Layout/MainLayout";
import ChatPage from "../Pages/ChatPage/ChatPage";
import SchedeleComponent from "../Pages/SchedulePage/SchedulePage";
import LoginPage from "../Pages/LoginPage/LoginPage";
import RegisterPage from "../Pages/RegisterPage/RegisterPage";
import { Navigate } from "react-router-dom";
import {
  ReadOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import SettingPage from "../Pages/SettingPage/SettingPage";
import BeforeEach from "./BeforeEach";
import NewChatPage from "../Pages/NewChatPage/NewChatPage.jsx";
import UserAgreementPage from "Pages/UserAgreementPage/UserAgreementPage.jsx";
import PrivacyPolicyPage from "Pages/PrivacyPolicyPage/PrivacyPolicyPage.jsx";

/**
 * @description 用于存放导航栏的需要权限的路由，同时 系统的导航菜单也是基于此路由表进行渲染的
 * @type {*}
 * */
const authRoutes = [
  // {
  //   path: "/chat",
  //   element: <ChatPage></ChatPage>,
  //   title: "学习",
  //   icon: <ReadOutlined></ReadOutlined>,
  // },
  // <<<<<<< HEAD
  // {
  //   path: "/schedele",
  //   element: <SchedeleComponent></SchedeleComponent>,
  //   title: "日程",
  //   icon: <ScheduleOutlined></ScheduleOutlined>,
  // },
  // {
  //   path: "/schedele",
  //   element: <SchedulePage></SchedulePage>,
  //   title: "日程",
  //   icon: <ScheduleOutlined></ScheduleOutlined>,
  // },
  // =======
  //   {
  //     path: "/schedele",
  //     element: <SchedeleComponent></SchedeleComponent>,
  //     title: "日程",
  //     icon: <ScheduleOutlined></ScheduleOutlined>,
  //   },
  // {
  //   path: "/schedeleDemo",
  //   element: <SchedulePage></SchedulePage>,
  //   title: "日程demo",
  //   icon: <ScheduleOutlined></ScheduleOutlined>,
  // },
  // >>>>>>> master
  // {
  //   path: "/todo",
  //   element: <ToDoComponent></ToDoComponent>,
  //   icon: <CheckSquareOutlined></CheckSquareOutlined>,
  //   title: "待办",
  // },
  // {
  //   path: "/contacts",
  //   element: <ContactsComponant></ContactsComponant>,
  //   icon: <ContactsOutlined></ContactsOutlined>,
  //   title: "通讯录",
  // },
  // {
  //   path: "/document",
  //   element: <DocumentPage></DocumentPage>,
  //   icon: <FolderOutlined></FolderOutlined>,
  //   title: "文档",
  // },
  {
    path: "/setting",
    element: <SettingPage></SettingPage>,
    icon: <SettingOutlined></SettingOutlined>,
    title: "设置",
  },
];

const routes = [
  {
    path: "/",
    element: <Navigate to='/newchat'></Navigate>,
  },
  {
    path: "/",
    element: (
      <BeforeEach authRoutes={authRoutes}>
        <MainLayout></MainLayout>
      </BeforeEach>
    ),
    children: authRoutes,
  },
  {
    path: '/useraggrement',
    element: <UserAgreementPage />
  },
  {
    path: '/privacypolicy',
    element: <PrivacyPolicyPage />
  },
  {
    path: "/chat",
    element: <ChatPage></ChatPage>,
    title: "学习",
    icon: <ReadOutlined></ReadOutlined>,
  },
  {
    path: "/login",
    element: <LoginPage></LoginPage>,
  },
  {
    path: "/register",
    element: <RegisterPage></RegisterPage>,
  },
  {
    path: '/newchat',
    element: <NewChatPage />
  },
  {
    path: '/newchat/:cid',
    element: <NewChatPage />
  }
];
export { authRoutes };

export default routes;

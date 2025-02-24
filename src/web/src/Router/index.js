import NewChatPage from "../Pages/NewChatPage/NewChatPage.jsx";
import UserAgreementPage from "Pages/UserAgreementPage/UserAgreementPage.jsx";
import PrivacyPolicyPage from "Pages/PrivacyPolicyPage/PrivacyPolicyPage.jsx";
import { Navigate } from "react-router-dom";
import NotFoundPage from "../Pages/NotFoundPage/NotFoundPage.jsx";

/**
 * @description 用于存放导航栏的需要权限的路由，同时 系统的导航菜单也是基于此路由表进行渲染的
 * @type {*}
 * */
const routes = [
  {
    path: "/",
    element: <Navigate to='/c/'></Navigate>,
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
    path: '/course',
    element: <NewChatPage />
  },
  {
    path: '/c/:courseId',
    element: <NewChatPage />
  },
  {
    path: '/c/',
    element: <NewChatPage />
  },
  {
    path: '/newchat',
    element: <Navigate to='/c/'></Navigate>
  },
  {
    path: '/newchat/:tmpId',
    element: <Navigate to='/c/'></Navigate>
  },
  {
    path: '/404',
    element: <NotFoundPage />
  },
  {
    path: '*',
    element: <Navigate to="/404" />
  }
];

export default routes;

import { useNavigate } from "react-router-dom";
import {authRoutes} from "../../Router/index";
import { Menu } from "antd";

/**
 *
 *@description 生成导航菜单项
 * @return {*} 
 */
const generateMenuItemlist = () => {
    const menuItemList = authRoutes.map(({ title, path, icon }) => ({ title, key:path, label:title, icon }));
    return menuItemList;
}


/**
 * @description 侧边栏内部的导航菜单
 */
const SiderNavMenu = ()=>{
    const navigator = useNavigate();
    const onClickMenuItem  = (e)=>{
        navigator(e.key)
    }
    return (
    <Menu
        style={{height:"100%"}}
        onClick={onClickMenuItem}
        items={generateMenuItemlist()}>
    </Menu>
    );

}


export default SiderNavMenu;
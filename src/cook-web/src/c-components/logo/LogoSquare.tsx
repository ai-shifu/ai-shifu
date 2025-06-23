import { Avatar } from 'antd';

export const LogoSquare = ({ size = 64, style = {} }) => {
  return (
    <Avatar
      size={size}
      src={require('@Assets/logos/logo64.png')}
      style={style}
      shape="square"
    />
  );
};

export default LogoSquare;

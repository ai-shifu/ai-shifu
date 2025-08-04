import { Avatar, AvatarImage } from '@/components/ui/Avatar';
import imgLogo64 from '@/c-assets/logos/logo64.png';

export const LogoSquare = ({
  // size = 64,
  style = {},
}) => {
  return (
    <Avatar style={style}>
      <AvatarImage src={imgLogo64.src} />
    </Avatar>
  );
};

export default LogoSquare;

import { Loader } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const LoadingBar = () => {
  const { t } = useTranslation();
  return (
    <span className='flex gap-[10px] items-center'>
      <Loader
        className='animate-spin'
        style={{ width: '15px', height: '15px' }}
      />
      {t('module.chat.thinking')}
    </span>
  );
};
export default LoadingBar;

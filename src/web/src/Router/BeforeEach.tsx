import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import store from 'store';

const BeforeEach = ({ children, authRoutes }) => {
  const navigate = useNavigate();
  window.addEventListener('apiError', ({ detail }) => {
    if (detail.code === 1005 || detail.code === 1001) {
      navigate('/login');
    }
  });
  const location = useLocation();
  const navigator = useNavigate();

  useEffect(() => {
    function checkAuth(pathname) {
      const cache = {};
      if (cache[pathname] === undefined) {
        const index = authRoutes.findIndex((route) => {
          return location.pathname === route.path;
        });
        cache[pathname] = index > -1;
        return index > -1;
      }
      return cache[pathname];
    }

    if (
      checkAuth(location.pathname) === true &&
      store.get('userInfo') === undefined
    ) {
      navigator('/login', { replace: true });
    }
  }, [authRoutes, location.pathname, navigator]);

  return children;
};
export default BeforeEach;

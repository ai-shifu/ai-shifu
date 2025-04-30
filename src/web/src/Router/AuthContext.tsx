import React, { createContext, useState } from 'react';
import Cookies from 'js-cookie';

export const AuthContext = createContext();

export const AuthProvider = (props) => {
  const [auth, setAuth] = useState(1);
  // const [auth, setAuth] = useState(!!Cookies.get('token'));

  return (
    <AuthContext.Provider value={{ auth, setAuth }}>
      {props.children}
    </AuthContext.Provider>
  );
};

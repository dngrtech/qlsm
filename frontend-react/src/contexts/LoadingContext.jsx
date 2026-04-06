import React, { createContext, useState, useContext } from 'react';

const LoadingContext = createContext();

export const useLoading = () => {
  return useContext(LoadingContext);
};

export const LoadingProvider = ({ children }) => {
  const [isLoadingGlobal, setIsLoadingGlobal] = useState(false);

  return (
    <LoadingContext.Provider value={{ isLoadingGlobal, setIsLoadingGlobal }}>
      {children}
    </LoadingContext.Provider>
  );
};

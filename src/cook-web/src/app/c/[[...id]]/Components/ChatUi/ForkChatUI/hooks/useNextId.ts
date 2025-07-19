import { useRef } from 'react';

let nextId = 0;
const getNextId = () => nextId++;

export default function useNextId(prefix = 'id-') {
  const idRef = useRef(`${prefix}${getNextId()}`);
  return idRef.current;
}

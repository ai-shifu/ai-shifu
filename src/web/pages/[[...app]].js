// pages/[[...app]].js

import { useState, useEffect } from 'react'
import App  from '../src/App'

function DefaultApp() {
  const [isMounted, setIsMounted] = useState(false)

  console.log('DefaultApp')
  useEffect(() => {
    setIsMounted(true)
  }, [])

  if (!isMounted) {
    return null
  }

  return <App />
}

export default DefaultApp

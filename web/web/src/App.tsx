import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { useUiStore } from './store/ui'
import './index.css'
import AppLayout from './components/layout/AppLayout'

// Initialize Zustand store
useUiStore.getState()

const appRoot = document.getElementById('root')

if (appRoot) {
  const root = createRoot(appRoot)
  root.render(
    <React.StrictMode>
      <AppLayout />
    </React.StrictMode>,
  )
}
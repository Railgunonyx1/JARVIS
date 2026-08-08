/// <reference types="vite/client" />

declare module '*.jsx' {
  import type { FC } from 'react'
  const component: FC<any>
  export default component
}

import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'rare-dx · 罕见病诊断辅助系统',
  description: '五层临床推理引擎',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">{children}</body>
    </html>
  )
}

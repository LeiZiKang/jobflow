import type { Metadata, Viewport } from "next";
import "@/styles/tokens.css";
import "@/styles/base.css";
import "@/styles/layout.css";
import "@/styles/views.css";

export const metadata: Metadata = {
  title: "Jobflow 控制台",
  description: "本地求职控制台：状态、投递、报告、Agent 运行记录。",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

const THEME_BOOT = `try{var t=localStorage.getItem("jobflow-theme");if(t==="light"||t==="dark"){document.documentElement.dataset.theme=t;document.cookie="jobflow-theme="+t+"; path=/; max-age=31536000; samesite=lax"}}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        {/* 首帧之前应用已保存的主题，避免先闪一下另一种颜色。 */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}

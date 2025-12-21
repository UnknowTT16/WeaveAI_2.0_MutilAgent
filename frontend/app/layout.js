// 删掉：import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

export const metadata = { title: "WeaveAI", description: "..." };

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body style={{ fontFamily: '"Segoe UI","Helvetica",Arial,sans-serif' }}>
        {children}
      </body>
    </html>
  );
}

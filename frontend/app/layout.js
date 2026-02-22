import { GeistSans } from 'geist/font/sans';
import { GeistMono } from 'geist/font/mono';
import "./globals.css";

import { WorkflowProvider } from "../contexts/WorkflowContext";
import { ThemeProvider } from "./components/ThemeProvider";

export const metadata = { 
  title: "WeaveAI 2.0 | Intelligent Market Insight", 
  description: "Supervisor-Worker + Multi-Agent Debate System",
};

export const viewport = {
  themeColor: '#f8fafc',
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className={`${GeistSans.variable} ${GeistMono.variable} font-sans antialiased`}>
        <a href="#main-content" className="skip-link">跳到主要内容</a>
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          <WorkflowProvider>{children}</WorkflowProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

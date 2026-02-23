import "./globals.css";
import type {Metadata} from "next";

export const metadata: Metadata = {
  title: "Video Auto Cut Web",
  description: "Web MVP for video_auto_cut"
};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

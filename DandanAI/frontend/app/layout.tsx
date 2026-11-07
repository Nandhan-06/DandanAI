import "./globals.css";
import { AuthProvider } from "@/lib/auth";
export const metadata = { title: "DandanAI — Legal Intelligence", description: "Decision-support platform for advocates" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body><AuthProvider>{children}</AuthProvider></body></html>;
}

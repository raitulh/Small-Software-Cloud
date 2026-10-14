import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Small Software Cloud — Ship small software simply",
  description: "A calm, developer-first control plane for small apps, APIs and background jobs.",
};
export const viewport: Viewport = { themeColor: "#f6f0e6", colorScheme: "light" };

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

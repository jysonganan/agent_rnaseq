import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import { ReactQueryProvider } from "@/providers/ReactQueryProvider"
import { AuthProvider } from "@/contexts/AuthContext"
import { AuthGuard } from "@/components/auth/AuthGuard"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "agent_rnaseq",
  description: "RNA-seq analysis pipeline agent",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <ReactQueryProvider>
          <AuthProvider>
            <AuthGuard>{children}</AuthGuard>
          </AuthProvider>
        </ReactQueryProvider>
      </body>
    </html>
  )
}

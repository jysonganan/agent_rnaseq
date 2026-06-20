import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import { ReactQueryProvider } from "@/providers/ReactQueryProvider"
import { AuthProvider } from "@/contexts/AuthContext"
import { AuthGuard } from "@/components/auth/AuthGuard"
import { Sidebar } from "@/components/layout/Sidebar"
import { MobileHeader } from "@/components/layout/MobileHeader"

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
            <AuthGuard>
              <div className="flex h-screen overflow-hidden">
                {/* Desktop sidebar — hidden on mobile */}
                <Sidebar />

                {/* Main column */}
                <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
                  {/* Mobile top bar — hidden on desktop */}
                  <MobileHeader />

                  <main className="flex-1 overflow-auto">
                    {children}
                  </main>
                </div>
              </div>
            </AuthGuard>
          </AuthProvider>
        </ReactQueryProvider>
      </body>
    </html>
  )
}

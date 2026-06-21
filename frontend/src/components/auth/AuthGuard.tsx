"use client"

import { useAuthContext } from "@/contexts/AuthContext"
import { ApiKeyModal } from "./ApiKeyModal"

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { apiKey, isBootstrapping } = useAuthContext()

  // Wait for localStorage validation to complete before rendering anything
  if (isBootstrapping) {
    return null
  }

  if (!apiKey) {
    return <ApiKeyModal />
  }

  return <>{children}</>
}

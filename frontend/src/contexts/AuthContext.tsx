"use client"

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react"
import { setApiKey as storeApiKey, setOn401Callback, validateApiKey } from "@/lib/api"

const LOCAL_STORAGE_KEY = "rnaseq_api_key"

interface AuthContextValue {
  apiKey: string | null
  isBootstrapping: boolean
  setApiKey: (key: string) => void
  clearApiKey: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [apiKey, setApiKeyState] = useState<string | null>(null)
  const [isBootstrapping, setIsBootstrapping] = useState(true)

  const clearApiKey = useCallback(() => {
    localStorage.removeItem(LOCAL_STORAGE_KEY)
    storeApiKey(null)
    setApiKeyState(null)
  }, [])

  const setApiKey = useCallback((key: string) => {
    localStorage.setItem(LOCAL_STORAGE_KEY, key)
    storeApiKey(key)
    setApiKeyState(key)
  }, [])

  useEffect(() => {
    // Wire 401 responses from any apiFetch call to clear the key
    setOn401Callback(clearApiKey)

    const stored = localStorage.getItem(LOCAL_STORAGE_KEY)
    if (!stored) {
      setIsBootstrapping(false)
      return
    }

    // Silently re-validate the stored key on every page load
    validateApiKey(stored).then((result) => {
      if (result === "valid") {
        storeApiKey(stored)
        setApiKeyState(stored)
      } else {
        // Expired or revoked — force re-login
        clearApiKey()
      }
      setIsBootstrapping(false)
    })
  }, [clearApiKey])

  return (
    <AuthContext.Provider value={{ apiKey, isBootstrapping, setApiKey, clearApiKey }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuthContext must be used within AuthProvider")
  return ctx
}

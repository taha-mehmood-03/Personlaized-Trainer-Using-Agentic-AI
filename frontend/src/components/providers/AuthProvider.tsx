'use client'

import React, { createContext, useContext, useEffect, useState } from 'react'

interface AuthContextType {
  userId: string | null
  isLoading: boolean
  login: (id: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType>({
  userId: null,
  isLoading: true,
  login: () => {},
  logout: () => {},
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [userId, setUserId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Read from cookies/localStorage on mount
    const stored = localStorage.getItem('sentimind_user_id')
    if (stored && stored !== 'undefined') {
      setUserId(stored)
    } else {
      setUserId('anonymous')
      localStorage.setItem('sentimind_user_id', 'anonymous')
    }
    setIsLoading(false)
  }, [])

  const login = (id: string) => {
    setUserId(id)
    localStorage.setItem('sentimind_user_id', id)
    document.cookie = `sentimind_user_id=${id}; path=/; max-age=31536000`
  }

  const logout = () => {
    setUserId(null)
    localStorage.removeItem('sentimind_user_id')
    document.cookie = 'sentimind_user_id=; path=/; expires=Thu, 01 Jan 1970 00:00:01 GMT'
  }

  return (
    <AuthContext.Provider value={{ userId, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)

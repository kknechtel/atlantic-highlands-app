"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { User, getMe, login as apiLogin, register as apiRegister, logout as apiLogout } from "@/lib/api";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Default user returned when auth is disabled
const DEFAULT_USER: User = {
  id: "default",
  email: "admin@atlantichighlands.local",
  username: "admin",
  full_name: "Admin",
  is_admin: true,
  is_active: true,
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(DEFAULT_USER);
  const [loading, setLoading] = useState(false);

  const login = async (email: string, password: string) => {
    setUser(DEFAULT_USER);
  };

  const register = async (email: string, username: string, password: string, fullName?: string) => {
    setUser(DEFAULT_USER);
  };

  const logout = () => {
    setUser(DEFAULT_USER);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

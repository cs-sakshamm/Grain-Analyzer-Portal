import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
} from "@/features/auth/auth-context";
import { setAccessToken, setUnauthorizedHandler } from "@/services/apiClient";
import { loginRequest, logoutRequest, refreshRequest } from "@/services/auth";
import type { User } from "@/types/auth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);

  const applySession = useCallback((token: string, nextUser: User) => {
    setAccessToken(token);
    setUser(nextUser);
    setStatus("authenticated");
  }, []);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setStatus("anonymous");
  }, []);

  /** Also used by the API client to recover from an expired access token. */
  const refreshSession = useCallback(async (): Promise<boolean> => {
    try {
      const data = await refreshRequest();
      applySession(data.access_token, data.user);
      return true;
    } catch {
      clearSession();
      return false;
    }
  }, [applySession, clearSession]);

  useEffect(() => {
    setUnauthorizedHandler(refreshSession);
    void refreshSession();
    return () => setUnauthorizedHandler(null);
  }, [refreshSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await loginRequest(email, password);
      applySession(data.access_token, data.user);
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, login, logout }),
    [status, user, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

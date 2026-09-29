"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import type { User } from "oidc-client-ts";
import { AuthConfigError } from "./config";
import { buildCognitoLogoutUrl, getUserManager } from "./userManager";
import { getRoles } from "./roles";

interface AuthContextValue {
  user: User | null;
  roles: string[];
  isLoading: boolean;
  configError: string | null;
  signIn: () => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;

    // Every setState here happens inside this async function, never synchronously in the
    // effect body itself: getUserManager() touches sessionStorage, so even the "it failed"
    // path has to be reached through an async tick, not a plain try/catch at the top level.
    async function init() {
      let userManager: ReturnType<typeof getUserManager>;
      try {
        userManager = getUserManager();
      } catch (err) {
        if (cancelled) return;
        setConfigError(
          err instanceof AuthConfigError ? err.message : "Failed to initialize authentication.",
        );
        setIsLoading(false);
        return;
      }

      const onUserLoaded = (loadedUser: User) => setUser(loadedUser);
      const onUserUnloaded = () => setUser(null);
      userManager.events.addUserLoaded(onUserLoaded);
      userManager.events.addUserUnloaded(onUserUnloaded);
      unsubscribe = () => {
        userManager.events.removeUserLoaded(onUserLoaded);
        userManager.events.removeUserUnloaded(onUserUnloaded);
      };

      const storedUser = await userManager.getUser();
      if (cancelled) return;
      setUser(storedUser && !storedUser.expired ? storedUser : null);
      setIsLoading(false);
    }

    void init();

    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

  const signIn = useCallback(() => {
    getUserManager()
      .signinRedirect()
      .catch(() => {
        setConfigError("Could not start sign-in. Please try again.");
      });
  }, []);

  const signOut = useCallback(() => {
    const userManager = getUserManager();
    userManager
      .removeUser()
      .catch(() => {})
      .finally(() => {
        window.location.href = buildCognitoLogoutUrl();
      });
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, roles: getRoles(user), isLoading, configError, signIn, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

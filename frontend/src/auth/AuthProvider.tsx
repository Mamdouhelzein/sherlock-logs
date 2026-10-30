import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { Session, SupabaseClient } from "@supabase/supabase-js";
import { getSupabase } from "../lib/supabase";
import { useQueryClient } from "@tanstack/react-query";

type AuthState = {
  client: SupabaseClient | null;
  session: Session | null;
  loading: boolean;
  error: string | null;
};
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({
  children,
  client: suppliedClient,
}: {
  children: ReactNode;
  client?: SupabaseClient | null;
}) {
  const queryClient = useQueryClient();
  const [configuration] = useState(() => {
    try {
      return {
        client: suppliedClient === undefined ? getSupabase() : suppliedClient,
        error: null,
      };
    } catch (error) {
      return { client: null, error: (error as Error).message };
    }
  });
  const [state, setState] = useState<AuthState>({
    ...configuration,
    session: null,
    loading: Boolean(configuration.client),
  });

  useEffect(() => {
    const client = configuration.client;
    if (!client) return;
    let active = true;
    // INITIAL_SESSION fires after Supabase finishes PKCE callback processing.
    // Keep this synchronous: awaiting other Supabase calls here can deadlock.
    const {
      data: { subscription },
    } = client.auth.onAuthStateChange((event, session) => {
      if (active && event === "SIGNED_OUT")
        queryClient.removeQueries({
          predicate: (query) => query.meta?.private === true,
        });
      if (active) setState({ client, session, loading: false, error: null });
    });
    void client.auth
      .getSession()
      .then(({ error }) => {
        if (active && error)
          setState({
            client,
            session: null,
            loading: false,
            error:
              "Your sign-in link or session could not be restored. Request a new link or sign in again.",
          });
      })
      .catch(() => {
        if (active)
          setState({
            client,
            session: null,
            loading: false,
            error: "Cannot restore your session. Try signing in again.",
          });
      });
    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, [configuration, queryClient]);

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("AuthProvider is required");
  return auth;
}

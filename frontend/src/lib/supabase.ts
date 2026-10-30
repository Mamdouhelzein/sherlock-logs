import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export function validateAuthConfig(url: string, key: string) {
  if (!url && !key) return null;
  try {
    const parsed = new URL(url);
    if (
      parsed.username ||
      parsed.password ||
      parsed.search ||
      parsed.hash ||
      parsed.pathname !== "/" ||
      !(
        parsed.protocol === "https:" ||
        (parsed.protocol === "http:" &&
          ["localhost", "127.0.0.1"].includes(parsed.hostname))
      ) ||
      !key.startsWith("sb_publishable_")
    )
      throw new Error("Invalid configuration");
    return { url: parsed.origin, key };
  } catch {
    throw new Error(
      "Set a valid Supabase project URL and publishable key in the root .env file.",
    );
  }
}

let instance: SupabaseClient | null = null;
export function getSupabase() {
  const config = validateAuthConfig(
    import.meta.env.VITE_SUPABASE_URL?.trim() ?? "",
    import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim() ?? "",
  );
  if (!config) return null;
  instance ??= createClient(config.url, config.key, {
    auth: {
      flowType: "pkce",
      detectSessionInUrl: true,
      persistSession: true,
      autoRefreshToken: true,
    },
  });
  return instance;
}

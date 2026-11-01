type AuthRequestFailure = { code?: string; status?: number };

// Keep provider payloads out of the UI while giving recoverable errors a next step.
export function emailRequestFailure(
  error: AuthRequestFailure,
  fallback: string,
): string {
  if (error.code === "over_email_send_rate_limit")
    return "Email delivery limit reached. Wait before requesting another link. If you already followed a confirmation link, try signing in instead.";
  if (error.code === "email_address_not_authorized")
    return "Email delivery is restricted for this project. Contact the project owner to enable delivery to this address.";
  if (error.status === 429)
    return "Too many requests. Please wait before trying again.";
  return fallback;
}

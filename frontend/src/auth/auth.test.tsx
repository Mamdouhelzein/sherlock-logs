import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { AuthPage, ProtectedPage } from "./AuthPages";
import { AuthProvider } from "./AuthProvider";
import { validateAuthConfig } from "../lib/supabase";

function renderWithoutProject(children: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <AuthProvider client={null}>{children}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it("disables account creation when no project is configured and explains setup", () => {
  renderWithoutProject(<AuthPage mode="register" />);
  expect(screen.getByRole("button", { name: "Create account" })).toBeDisabled();
  expect(screen.getByLabelText("Email address")).toBeDisabled();
  expect(screen.getByText("Connect Supabase to unlock sign-in.")).toBeVisible();
  expect(
    screen.getByRole("link", { name: /Supabase setup guide/ }),
  ).toHaveAttribute("href", expect.stringContaining("supabase/README.md"));
});

it("does not reveal an account or administrator content without a configured project", () => {
  renderWithoutProject(<ProtectedPage admin />);
  expect(screen.getByText("Connect Supabase to unlock sign-in.")).toBeVisible();
  expect(
    screen.queryByText("Administrator access confirmed."),
  ).not.toBeInTheDocument();
});

it("accepts only safe project origins and publishable keys", () => {
  expect(validateAuthConfig("", "")).toBeNull();
  expect(
    validateAuthConfig("https://example.supabase.co", "sb_publishable_test"),
  ).toEqual({ url: "https://example.supabase.co", key: "sb_publishable_test" });
  for (const [url, key] of [
    ["https://example.supabase.co", "sb_secret_test"],
    ["http://example.com", "sb_publishable_test"],
    ["https://example.com/path", "sb_publishable_test"],
    ["", "sb_publishable_test"],
    ["https://user:password@example.com", "sb_publishable_test"],
  ])
    expect(() => validateAuthConfig(url, key)).toThrow();
});

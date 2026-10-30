import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import { systemFixture } from "./test/fixture";

function renderWorkspace(path = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider client={null}>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it("recovers from API failure through a manual retry", async () => {
  const request = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("Network error"))
    .mockResolvedValue({ ok: true, json: async () => systemFixture });
  vi.stubGlobal("fetch", request);
  renderWorkspace();
  expect(await screen.findByText("API unavailable")).toBeInTheDocument();
  expect(
    screen.getByText("Event collection coverage is verified separately.", {
      exact: false,
    }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Check again" }));
  expect(await screen.findByText("API reachable")).toBeInTheDocument();
  expect(screen.getByText("The model is not trained.")).toBeInTheDocument();
  expect(request).toHaveBeenCalledTimes(2);
});

it("keeps setup and architecture navigation usable when the API is unavailable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Offline")));
  renderWorkspace();
  await userEvent.click(
    screen.getByRole("link", { name: /System architecture/ }),
  );
  expect(
    screen.getByRole("heading", { name: "Follow the signal." }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("link", { name: /Local setup/ }));
  expect(
    screen.getByRole("heading", { name: "Start the investigation." }),
  ).toBeInTheDocument();
});

it("provides a return path for unknown routes", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => systemFixture }),
  );
  renderWorkspace("/missing");
  expect(
    screen.getByRole("heading", { name: "This case file is missing." }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: /Return to overview/ }),
  ).toHaveAttribute("href", "/");
});

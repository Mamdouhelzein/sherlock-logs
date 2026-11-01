import { expect, it } from "vitest";
import { emailRequestFailure } from "./errors";

it("distinguishes email delivery limits from general request limits", () => {
  expect(
    emailRequestFailure(
      { code: "over_email_send_rate_limit", status: 429 },
      "Request failed",
    ),
  ).toMatch(/Email delivery limit reached.*try signing in/);
  expect(emailRequestFailure({ status: 429 }, "Request failed")).toMatch(
    /Too many requests/,
  );
});

it("explains restricted email delivery without changing unknown error messages", () => {
  expect(
    emailRequestFailure(
      { code: "email_address_not_authorized" },
      "Request failed",
    ),
  ).toMatch(/Contact the project owner/);
  expect(emailRequestFailure({ code: "unexpected" }, "Request failed")).toBe(
    "Request failed",
  );
});

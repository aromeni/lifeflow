import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API_URL = "http://localhost:8010";
const MUTATION_HEADERS = { "X-LifeFlow-CSRF": "1" };

type Proposal = {
  id: string;
  action_type: "create_task" | "create_gmail_draft" | "create_calendar_event";
  source_refs: string[];
  payload: Record<string, unknown>;
  payload_hash: string;
  version: number;
  status: string;
  origin_fingerprint: string;
  approval: null | {
    action_type: string;
    proposal_version: number;
    payload: Record<string, unknown>;
    payload_hash: string;
    binding_hash: string;
  };
  execution: null | {
    id: string;
    result: Record<string, unknown>;
    executed_payload: Record<string, unknown>;
  };
  audit_events: { event_type: string }[];
};

async function proposalList(request: APIRequestContext): Promise<Proposal[]> {
  const response = await request.get(`${API_URL}/action-proposals`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()).proposals as Proposal[];
}

async function startIsolatedDemo(page: Page) {
  await page.goto("/");
  const login = await page.request.post(`${API_URL}/auth/dev-login`, {
    headers: MUTATION_HEADERS,
    data: {
      email: `playwright-${Date.now()}@example.com`,
      display_name: "Playwright Approval User",
    },
  });
  expect(login.ok()).toBeTruthy();
  const demo = await page.request.post(`${API_URL}/demo/start`, {
    headers: MUTATION_HEADERS,
  });
  expect(demo.ok()).toBeTruthy();
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { name: "Set up your demo" })).toBeVisible();
  await page.getByRole("button", { name: "Finish and open Today" }).click();
  await expect(page).toHaveURL(/\/today/);
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version 1 · complete/, {
    timeout: 15_000,
  });
}

test("approval inbox preserves exact, grounded, idempotent proposal transitions", async ({
  page,
}) => {
  await startIsolatedDemo(page);
  const initial = await proposalList(page.request);
  expect(initial).toHaveLength(3);
  expect(new Set(initial.map((proposal) => proposal.origin_fingerprint)).size).toBe(3);
  expect(initial.flatMap((proposal) => proposal.source_refs)).not.toContain("em-004");

  await page.getByTestId("approval-inbox-link").click();
  await expect(page).toHaveURL(/\/approvals/);
  await expect(page.getByRole("heading", { name: "Approval inbox" })).toBeVisible();
  await expect(page.getByText("3 proposals · simulated execution only")).toBeVisible();

  const draft = page.getByTestId("proposal-create_gmail_draft");
  const draftPayload = initial.find((proposal) => proposal.action_type === "create_gmail_draft")!;
  await draft.getByText(/Evidence \(1 source/).click();
  await expect(draft.getByText(new RegExp(`ref ${draftPayload.source_refs[0]}`))).toBeVisible();
  for (const [field, label] of [
    ["to", "To"],
    ["subject", "Subject"],
    ["body", "Body"],
    ["thread_id", "Thread id"],
  ]) {
    await expect(
      draft.getByTestId("payload-preview-create_gmail_draft").getByText(label, { exact: true }),
    ).toBeVisible();
    expect(Object.hasOwn(draftPayload.payload, field)).toBeTruthy();
  }
  await expect(page.getByText(/velvet-mail/i)).toHaveCount(0);
  await expect(page.getByText(/forward every message/i)).toHaveCount(0);

  const task = page.getByTestId("proposal-create_task");
  const originalTask = initial.find((proposal) => proposal.action_type === "create_task")!;
  await task.getByRole("button", { name: "Approve exact payload" }).click();
  await expect(page.getByTestId("proposal-status-create_task")).toHaveText("approved");
  await expect(task.getByTestId("approval-binding")).toContainText("Binding SHA-256");

  await task.getByRole("button", { name: "Edit exact payload" }).click();
  const editedPayload = {
    ...originalTask.payload,
    title: "Edited and freshly reviewed internal task",
  };
  await task.getByTestId("payload-editor-create_task").fill(JSON.stringify(editedPayload, null, 2));
  const editResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url() === `${API_URL}/action-proposals/${originalTask.id}`,
  );
  await task.getByRole("button", { name: "Save and invalidate approval" }).click();
  const editResponse = await editResponsePromise;
  expect(
    editResponse.status(),
    `${editResponse.request().postData()}\n${await editResponse.text()}`,
  ).toBe(200);
  await expect(page.getByTestId("proposal-status-create_task")).toHaveText("edited");
  await expect(task.getByText(/proposal version 2/)).toBeVisible();
  await expect(task.getByTestId("approval-binding")).toHaveCount(0);

  const editedTaskResponse = await page.request.get(
    `${API_URL}/action-proposals/${originalTask.id}`,
  );
  const editedTask = (await editedTaskResponse.json()) as Proposal;
  expect(editedTask.version).toBe(originalTask.version + 1);
  expect(editedTask.approval).toBeNull();
  expect(editedTask.audit_events.map((event) => event.event_type)).toContain(
    "approval.invalidated",
  );

  const staleEdit = await page.request.patch(`${API_URL}/action-proposals/${originalTask.id}`, {
    headers: MUTATION_HEADERS,
    data: {
      expected_version: originalTask.version,
      action_type: originalTask.action_type,
      payload: editedPayload,
    },
  });
  expect(staleEdit.status()).toBe(409);
  expect((await staleEdit.json()).error.code).toBe("stale_version");

  await task.getByRole("button", { name: "Approve exact payload" }).click();
  await expect(page.getByTestId("proposal-status-create_task")).toHaveText("approved");
  const reboundResponse = await page.request.get(`${API_URL}/action-proposals/${originalTask.id}`);
  const rebound = (await reboundResponse.json()) as Proposal;
  expect(rebound.approval?.action_type).toBe(rebound.action_type);
  expect(rebound.approval?.proposal_version).toBe(rebound.version);
  expect(rebound.approval?.payload).toEqual(rebound.payload);
  expect(rebound.approval?.payload_hash).toBe(rebound.payload_hash);

  await task.getByRole("button", { name: "Run approved simulation" }).click();
  await expect(page.getByTestId("proposal-status-create_task")).toHaveText("executed");
  await expect(task.getByTestId("execution-result")).toContainText("succeeded");
  const firstExecutionResponse = await page.request.get(
    `${API_URL}/action-proposals/${originalTask.id}`,
  );
  const firstExecution = (await firstExecutionResponse.json()) as Proposal;
  const replayResponse = await page.request.post(
    `${API_URL}/action-proposals/${originalTask.id}/execute`,
    { headers: MUTATION_HEADERS },
  );
  expect(replayResponse.ok()).toBeTruthy();
  const replay = (await replayResponse.json()) as Proposal;
  expect(replay.execution?.id).toBe(firstExecution.execution?.id);
  expect(replay.execution?.result).toEqual(firstExecution.execution?.result);
  expect(replay.execution?.executed_payload).toEqual(rebound.approval?.payload);

  const calendar = page.getByTestId("proposal-create_calendar_event");
  const originalCalendar = initial.find(
    (proposal) => proposal.action_type === "create_calendar_event",
  )!;
  await calendar.getByRole("button", { name: "Reject" }).click();
  await expect(page.getByTestId("proposal-status-create_calendar_event")).toHaveText("rejected");
  await expect(calendar.getByRole("button", { name: "Approve exact payload" })).toHaveCount(0);
  const terminalApproval = await page.request.post(
    `${API_URL}/action-proposals/${originalCalendar.id}/approve`,
    {
      headers: MUTATION_HEADERS,
      data: {
        expected_version: originalCalendar.version,
        action_type: originalCalendar.action_type,
        displayed_payload_hash: originalCalendar.payload_hash,
      },
    },
  );
  expect(terminalApproval.status()).toBe(409);
  expect((await terminalApproval.json()).error.code).toBe("invalid_transition");

  const beforeRegeneration = await proposalList(page.request);
  await page.getByRole("link", { name: /Back to Today/ }).click();
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-status")).toContainText(/version 2 · complete/, {
    timeout: 15_000,
  });
  const afterRegeneration = await proposalList(page.request);
  expect(afterRegeneration).toHaveLength(3);
  expect(afterRegeneration.map((proposal) => proposal.id).sort()).toEqual(
    beforeRegeneration.map((proposal) => proposal.id).sort(),
  );
  expect(afterRegeneration.map((proposal) => proposal.origin_fingerprint).sort()).toEqual(
    beforeRegeneration.map((proposal) => proposal.origin_fingerprint).sort(),
  );
  expect(afterRegeneration.flatMap((proposal) => proposal.source_refs)).not.toContain("em-004");
  expect(
    JSON.stringify(afterRegeneration.map((proposal) => proposal.payload)).toLowerCase(),
  ).not.toContain("velvet-mail");
  const taskAfter = afterRegeneration.find((proposal) => proposal.id === originalTask.id)!;
  const calendarAfter = afterRegeneration.find((proposal) => proposal.id === originalCalendar.id)!;
  expect(taskAfter.status).toBe("executed");
  expect(taskAfter.payload).toEqual(editedPayload);
  expect(calendarAfter.status).toBe("rejected");
});

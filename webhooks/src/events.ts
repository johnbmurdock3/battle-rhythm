// What to do with each verified event. Pure functions: payload and prior state
// in, a plan out. No I/O here, so every rule is testable on a fixture alone.

import type { WorkflowState } from "./store.ts";

export interface Plan {
  outcome: "processed" | "ignored";
  detail: string;
  message?: string; // sent to Discord when present
  state?: WorkflowState; // written after the message is delivered (or now, if there is none)
}

type Json = Record<string, any>;

const FAILING = new Set(["failure", "timed_out", "startup_failure"]);
// Conclusions that say nothing about whether the code is healthy.
const NO_SIGNAL = new Set(["cancelled", "skipped", "neutral", "action_required", "stale"]);

export function plan(event: string, p: Json, prev: WorkflowState | null, env: string): Plan {
  const tag = `[${env}]`;
  switch (event) {
    case "ping":
      return {
        outcome: "processed",
        detail: `ping from hook ${p.hook_id}`,
        message: `${tag} Webhook connected for ${p.repository?.full_name}: hook ${p.hook_id}, events ${(p.hook?.events ?? []).join(", ")}`,
      };
    case "workflow_run":
      return planWorkflowRun(p, prev, tag);
    case "push":
      return planPush(p, tag);
    default:
      return { outcome: "ignored", detail: `no handler for ${event}` };
  }
}

export function workflowKey(p: Json): string | null {
  const r = p.workflow_run;
  return r ? `${r.workflow_id}:${r.head_branch}` : null;
}

function planWorkflowRun(p: Json, prev: WorkflowState | null, tag: string): Plan {
  const r = p.workflow_run;
  if (!r) return { outcome: "ignored", detail: "workflow_run without a run" };
  if (p.action !== "completed") return { outcome: "ignored", detail: `workflow_run ${p.action}` };

  const attempt = r.run_attempt ?? 1;
  const label = `${r.name} on ${r.head_branch} (run #${r.run_number}${attempt > 1 ? `, attempt ${attempt}` : ""})`;

  // GitHub does not promise delivery order. A run that finished earlier can
  // arrive after a newer one; it must not rewrite the current state.
  if (prev && (r.run_number < prev.runNumber || (r.run_number === prev.runNumber && attempt <= prev.runAttempt))) {
    return { outcome: "ignored", detail: `stale: ${label} is not newer than run #${prev.runNumber}.${prev.runAttempt}` };
  }
  if (NO_SIGNAL.has(r.conclusion)) {
    return { outcome: "ignored", detail: `${label} ${r.conclusion}` };
  }

  const state: WorkflowState = {
    key: `${r.workflow_id}:${r.head_branch}`,
    runId: r.id,
    runNumber: r.run_number,
    runAttempt: attempt,
    conclusion: r.conclusion,
    updatedAt: r.updated_at ?? new Date().toISOString(),
  };
  const wasFailing = prev ? FAILING.has(prev.conclusion) : false;

  if (FAILING.has(r.conclusion)) {
    if (wasFailing) return { outcome: "processed", detail: `${label} still failing; alert already sent`, state };
    return {
      outcome: "processed",
      detail: `${label} ${r.conclusion}`,
      message: `${tag} CI ${r.conclusion.replace("_", " ")}: ${label}\n${r.html_url}`,
      state,
    };
  }
  if (r.conclusion === "success" && wasFailing) {
    return {
      outcome: "processed",
      detail: `${label} recovered`,
      message: `${tag} CI recovered: ${label} passed after run #${prev!.runNumber} failed\n${r.html_url}`,
      state,
    };
  }
  return { outcome: "processed", detail: `${label} ${r.conclusion}`, state };
}

function planPush(p: Json, tag: string): Plan {
  const branch = String(p.ref ?? "").replace(/^refs\/heads\//, "");
  const isDefault = p.repository?.default_branch === branch;
  const who = p.pusher?.name ?? p.sender?.login ?? "someone";
  if (p.deleted) {
    return {
      outcome: "processed",
      detail: `${p.ref} deleted`,
      message: `${tag} Branch deleted: ${branch} by ${who}`,
    };
  }
  if (p.forced && isDefault) {
    return {
      outcome: "processed",
      detail: `force-push to ${branch}`,
      message: `${tag} Force-push to ${branch} by ${who}: ${String(p.before).slice(0, 7)} -> ${String(p.after).slice(0, 7)}\n${p.compare}`,
    };
  }
  const n = Array.isArray(p.commits) ? p.commits.length : 0;
  return { outcome: "processed", detail: `${n} commit${n === 1 ? "" : "s"} to ${branch}` };
}

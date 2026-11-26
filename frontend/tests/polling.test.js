import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import { computed, nextTick, ref, watch } from "vue";
import { cleanAnswer } from "../src/markdown.js";
import { LANGUAGES, messageTime, responseDuration, translate } from "../src/locale.js";

test("idle makes no requests; active jobs update model state without health polling", async () => {
  const source = readFileSync(
    new URL("../src/App.vue", import.meta.url),
    "utf8",
  );
  const script = source
    .match(/<script setup>([\s\S]*?)<\/script>/)[1]
    .replace(/^import .* from .*;\r?$/gm, "");
  const timers = new Map(),
    notificationTimers = new Map(),
    calls = [],
    serverJobs = [];
  let mounted,
    unmounted,
    nextTimer = 0;
  const context = {
    cleanAnswer, LANGUAGES, messageTime, responseDuration, translate,
    computed,
    ref,
    watch,
    nextTick,
    localStorage: { getItem: () => null, setItem: () => {} },
    document: { documentElement: { dataset: {}, style: {} } },
    crypto: { randomUUID: () => "0123456789abcdef0123456789abcdef" },
    onMounted: (fn) => {
      mounted = fn;
    },
    onUnmounted: (fn) => {
      unmounted = fn;
    },
    setTimeout: (fn, delay) => {
      (delay === 5000 ? notificationTimers : timers).set(++nextTimer, fn);
      return nextTimer;
    },
    clearTimeout: (id) => { timers.delete(id); notificationTimers.delete(id); },
    fetch: async (path, options = {}) => {
      calls.push(path);
      let value;
      if (path === "/api/health") value = { model: { state: "unloaded" } };
      else if (path === "/api/assets") value = [];
      else if (path === "/api/chats") value = [];
      else if (path === "/api/jobs" && options.method === "POST") {
        value = {
          id: String(serverJobs.length + 1),
          created_at: String(serverJobs.length + 1).padStart(5, "0"),
          status: "queued",
          request: JSON.parse(options.body),
        };
        serverJobs.unshift(value);
      } else if (path === "/api/jobs") value = serverJobs;
      else throw new Error(`Unexpected endpoint: ${path}`);
      return { ok: true, json: async () => structuredClone(value) };
    },
  };
  runInNewContext(
    script +
      "\nthis.app = { queue, poll, health, jobs, question, conversation };",
    context,
  );
  async function tick() {
    assert.equal(timers.size, 1);
    const [id, callback] = timers.entries().next().value;
    timers.delete(id);
    await callback();
    await nextTick();
  }

  await mounted();
  await nextTick();
  assert.equal(timers.size, 0);
  assert.equal(calls.filter((p) => p === "/api/health").length, 1);

  await context.app.queue("load");
  await nextTick();
  serverJobs[0].status = "running";
  await tick();
  assert.equal(timers.size, 1);
  serverJobs[0] = {
    ...serverJobs[0],
    status: "completed",
    finished_at: "2026-11-17T04:00:00Z",
    model: { state: "loaded" },
  };
  await tick();
  assert.equal(context.app.health.value.model.state, "loaded");
  assert.equal(timers.size, 0);
  const idleCalls = calls.length;
  await context.app.poll();
  assert.equal(calls.length, idleCalls);

  await context.app.queue("unload");
  await nextTick();
  serverJobs[0] = {
    ...serverJobs[0],
    status: "completed",
    finished_at: "2026-11-17T04:01:00Z",
    model: { state: "unloaded" },
  };
  await tick();
  assert.equal(context.app.health.value.model.state, "unloaded");
  assert.equal(timers.size, 0);

  await context.app.queue("load");
  await nextTick();
  serverJobs[0] = { ...serverJobs[0], status: "failed", error: "Test failure" };
  await tick();
  assert.equal(context.app.jobs.value[0].status, "failed");
  assert.equal(timers.size, 0);
  assert.equal(calls.filter((p) => p === "/api/health").length, 1);
  context.app.question.value = "Which flight has the highest PM2.5?";
  await context.app.queue("analyze");
  await nextTick();
  assert.equal(serverJobs[0].request.history.length, 0);
  assert.equal(serverJobs[0].request.chat_id.length, 32);
  assert.equal(context.app.question.value, "");
  serverJobs[0] = {
    ...serverJobs[0],
    status: "completed",
    answer: "TEST STUB: flight A",
    finished_at: "2026-11-17T04:02:00Z",
    model: { state: "loaded" },
  };
  await tick();
  context.app.question.value = "And its altitude setting?";
  await context.app.queue("analyze");
  await nextTick();
  assert.deepEqual(serverJobs[0].request.history, [
    { role: "user", content: "Which flight has the highest PM2.5?" },
    { role: "assistant", content: "TEST STUB: flight A" },
  ]);
  assert.equal(context.app.conversation.value.length, 2);
  unmounted();
  assert.equal(notificationTimers.size, 0);
});

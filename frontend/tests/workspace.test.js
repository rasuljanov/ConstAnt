import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import { computed, nextTick, ref, watch } from "vue";
import { cleanAnswer } from "../src/markdown.js";
import { LANGUAGES, messageTime, responseDuration, translate } from "../src/locale.js";

const source = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8")
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import .* from .*;\r?$/gm, "");
let nextId = 100;
async function mountWorkspace(serverJobs, serverAssets, preferences = new Map(), metadata = new Map(), contents = new Map()) {
  let mounted, unmounted, nextTimer = 0;
  const timers = new Map();
  const calls = [];
  const clipboard = [];
  const context = {
    computed, nextTick, ref, watch, cleanAnswer, LANGUAGES, messageTime, responseDuration, translate,
    navigator: { clipboard: { writeText: async (text) => clipboard.push(text) } },
    localStorage: { getItem: (key) => preferences.get(key), setItem: (key, value) => preferences.set(key, value) },
    document: { documentElement: { dataset: {}, style: {} }, querySelector: () => ({ focus() {} }) },
    window: { innerWidth: 1280, innerHeight: 720 },
    matchMedia: () => ({ matches: true }),
    crypto: { randomUUID: () => String(++nextId).padStart(32, "0") },
    onMounted: (fn) => { mounted = fn; }, onUnmounted: (fn) => { unmounted = fn; },
    setTimeout: (fn, delay) => { timers.set(++nextTimer, { fn, delay }); return nextTimer; }, clearTimeout: (id) => timers.delete(id),
    FormData: class { constructor() { this.values = new Map(); } append(key, value) { this.values.set(key, value); } },
    XMLHttpRequest: class {
      constructor() { this.upload = {}; }
      open() {}
      send(body) {
        const file = body.values.get("file");
        const item = { id: "video-upload", name: file.name, kind: "video", role: "auto", bytes: file.size, info: { duration_seconds: 600 } };
        serverAssets.push(item);
        this.status = 201;
        this.responseText = JSON.stringify(item);
        this.onload();
      }
    },
    fetch: async (path, options = {}) => {
      calls.push({ path, options });
      if (contents.has(path)) return contents.get(path);
      let value;
      if (path === "/api/health") value = { model: { state: "unloaded" } };
      else if (path === "/api/assets") value = serverAssets;
      else if (path === "/api/chats") {
        const chats = new Map();
        for (const run of [...serverJobs].reverse())
          if (run.request.action === "analyze") chats.set(run.request.chat_id, { id: run.request.chat_id, title: metadata.get(run.request.chat_id)?.auto_title ? null : run.request.question, updated_at: run.created_at, pinned: false, ...metadata.get(run.request.chat_id) });
        value = [...chats.values()];
      } else if (path.startsWith("/api/chats/") && options.method === "PATCH") {
        const id = path.split("/").at(-1);
        const changes = { ...metadata.get(id), ...JSON.parse(options.body) };
        metadata.set(id, changes);
        const run = serverJobs.find((r) => r.request.chat_id === id);
        value = { id, title: changes.auto_title ? null : run.request.question, updated_at: run.created_at, pinned: false, ...changes };
      } else if (path.startsWith("/api/chats/") && options.method === "DELETE") {
        const id = path.split("/").at(-1);
        for (let i = serverJobs.length - 1; i >= 0; i--)
          if (serverJobs[i].request.chat_id === id) serverJobs.splice(i, 1);
        metadata.delete(id);
        value = { deleted: id };
      } else if (path.startsWith("/api/jobs?chat_id=")) {
        value = serverJobs.filter((run) => run.request.chat_id === path.split("=")[1]);
      } else if (path === "/api/jobs" && options.method === "POST") {
        value = { id: String(++nextId), created_at: String(nextId), status: "queued", request: JSON.parse(options.body) };
        if (value.request.action === "analyze" && !serverJobs.some((run) => run.request.chat_id === value.request.chat_id))
          metadata.set(value.request.chat_id, { auto_title: true });
        serverJobs.unshift(value);
      } else if (path.endsWith("/cancel")) value = { cancel_requested: true };
      else if (path === "/api/jobs") value = serverJobs;
      else if (path.includes("/content?offset=")) value = await contents.get(path.split("/")[3]);
      else if (path.startsWith("/api/assets/") && options.method === "DELETE") {
        const id = path.split("/").at(-1);
        serverAssets.splice(serverAssets.findIndex((a) => a.id === id), 1);
        value = { deleted: id };
      } else throw new Error("Unexpected request: " + path);
      return { ok: true, json: async () => structuredClone(value) };
    },
  };
  runInNewContext(source + "\nthis.app = { assets, jobs, chats, chatId, selected, conversation, question, queue, poll, newChat, setChat, askDelete, deleteResource, deleteDialog, deleteTarget, uploadFiles, error, notice, size, theme, setTheme, orderedChats, chatMenu, chatMenuElement, openChatMenu, closeChatMenu, chatMenuKey, beginRename, renameDialog, renameTitle, saveChatName, toggleChatPin, askDeleteChat, chatDeleteDialog, deleteChat, chatIsActive, refresh, profile, profileName, profileRole, profileStatus, saveProfile, attachmentMenuOpen, attachmentMenu, toggleAttachmentMenu, attachmentMenuKey, chooseUpload, openPanel, addSelectedToChat, attachments, drawer, input, panel, inspect, fileContent, fileError, fileLoading, loadFileContent, sourceScope, viewSources, visibleAssets, inspectTables, notificationHost, videoError, videoPlaybackError, language, setLanguage, t, copiedMessage, copyMessage, thinkingText, pendingRun, chatBusy, stopJob, currentTitle, chatTitle, pendingUpdates, progressPercent };", context);
  await mounted();
  await nextTick();
  return { app: context.app, calls, document: context.document, timers, clipboard, navigator: context.navigator, unmount: () => unmounted() };
}

function savedRun() {
  return { id: "saved", created_at: "1", status: "completed", answer: "TEST STUB: saved measurements.",
    request: { action: "analyze", chat_id: "f".repeat(32), question: "Review the earlier flight.", asset_ids: ["pm-1"] } };
}

test("new chat stays unnamed until its first response title arrives, then persists without idle polling", async () => {
  const jobs = [], metadata = new Map(), preferences = new Map();
  const { app, timers, calls, unmount } = await mountWorkspace(jobs, [], preferences, metadata);
  async function tick() {
    await nextTick();
    const [id, timer] = [...timers.entries()].find(([, timer]) => timer.delay === 2500);
    timers.delete(id);
    await timer.fn();
    await nextTick();
  }
  app.question.value = "What is happening on this construction site?";
  await app.queue("analyze");
  assert.equal(app.currentTitle.value, "New chat");
  assert.equal(app.chatTitle(app.chats.value[0]), "New chat");
  assert.equal(app.chatBusy.value, true);
  app.setLanguage("uz");
  assert.equal(app.currentTitle.value, "Yangi suhbat");
  jobs[0] = { ...jobs[0], status: "completed", answer: "TEST STUB: excavators are loading soil.", title_pending: true };
  await tick();
  assert.equal(app.currentTitle.value, "Yangi suhbat");
  assert.equal(app.conversation.value[0].answer, jobs[0].answer);
  assert.equal(app.chatBusy.value, false);
  assert.equal(app.pendingUpdates.value.length, 1);
  metadata.set(app.chatId.value, { title: "Site Excavation Activity", auto_title: false });
  jobs[0].title_pending = false;
  await tick();
  assert.equal(app.currentTitle.value, "Site Excavation Activity");
  assert.equal(app.pendingUpdates.value.length, 0);
  assert.equal(timers.size, 0);
  const count = calls.length;
  await app.poll();
  assert.equal(calls.length, count);
  const restored = await mountWorkspace(jobs, [], preferences, metadata);
  assert.equal(restored.app.chats.value[0].title, "Site Excavation Activity");
  assert.equal(restored.app.conversation.value.length, 0);
  unmount();
  restored.unmount();
});

test("language persists and accompanies new requests without modifying saved answers", async () => {
  const preferences = new Map(), jobs = [savedRun()];
  const { app, document } = await mountWorkspace(jobs, [], preferences);
  app.setLanguage("ko");
  assert.equal(document.documentElement.lang, "ko");
  assert.equal(app.t("New chat"), "새 대화");
  assert.equal(preferences.get("constant-language"), "ko");
  app.question.value = "Question remains in English.";
  await app.queue("analyze");
  assert.equal(jobs[0].request.language, "ko");
  assert.equal(jobs[0].request.question, "Question remains in English.");
  assert.equal(jobs[1].answer, "TEST STUB: saved measurements.");
  const restored = await mountWorkspace([], [], preferences);
  assert.equal(restored.app.language.value, "ko");
  restored.app.setLanguage("unsupported");
  assert.equal(restored.app.language.value, "ko");
});

test("copy uses the displayed answer, gives temporary feedback, and handles clipboard denial", async () => {
  const { app, clipboard, navigator, timers, unmount } = await mountWorkspace([], []);
  const run = { id: "copy-test", answer: "**TEST** answer. [Selected tables]" };
  await app.copyMessage(run);
  assert.deepEqual(clipboard, ["**TEST** answer."]);
  assert.equal(app.copiedMessage.value, run.id + ":response");
  assert.match(run.answer, /Selected tables/);
  const reset = [...timers.values()].find((t) => t.delay === 2000);
  reset.fn();
  assert.equal(app.copiedMessage.value, "");
  navigator.clipboard.writeText = async () => { throw new Error("TEST DENIAL"); };
  await app.copyMessage(run);
  assert.match(app.error.value, /Could not copy/);
  unmount();
  assert.equal(timers.size, 0);
});

test("request copy preserves the exact question and has separate feedback from the response", async () => {
  const { app, clipboard, unmount } = await mountWorkspace([], []);
  const run = { id: "same-turn", request: { question: "What does [Selected tables] mean?\nKeep this line." }, answer: "**TEST** reply. [Selected tables]" };
  await app.copyMessage(run, "request");
  assert.equal(clipboard[0], run.request.question);
  assert.equal(app.copiedMessage.value, "same-turn:request");
  await app.copyMessage(run);
  assert.equal(clipboard[1], "**TEST** reply.");
  assert.equal(app.copiedMessage.value, "same-turn:response");
  assert.equal(app.t("Copy request"), "Copy request");
  app.setLanguage("uz");
  assert.equal(app.t("Copy request"), "Savolni nusxalash");
  app.setLanguage("ko");
  assert.equal(app.t("Copy request"), "질문 복사");
  unmount();
});

test("the active chat exposes a single stop action and technical planner stages show Thinking", async () => {
  const { app, calls } = await mountWorkspace([], []);
  app.question.value = "TEST QUESTION";
  await app.queue("analyze");
  const active = app.pendingRun.value;
  active.status = "running";
  active.stage = "Planning a measurement query";
  assert.equal(app.thinkingText(active), "Thinking…");
  await Promise.all([app.stopJob(active), app.stopJob(active)]);
  assert.equal(calls.filter((c) => c.path.endsWith("/cancel")).length, 1);
  assert.equal(active.cancel_requested, true);
  assert.equal(app.thinkingText(active), "Stopping…");
  active.status = "cancelled";
  assert.equal(app.chatBusy.value, false);
  assert.equal(app.pendingRun.value, undefined);
});

test("the worker marker follows actual scan counts and stays within the track", async () => {
  const { app, unmount } = await mountWorkspace([], []);
  assert.equal(app.progressPercent(undefined), 0);
  assert.equal(app.progressPercent({ completed: 0, total: 0 }), 0);
  assert.equal(app.progressPercent({ completed: 30, total: 391 }), 30 / 391 * 100);
  assert.equal(app.progressPercent({ completed: 391, total: 391 }), 100);
  assert.equal(app.progressPercent({ completed: 400, total: 391 }), 100);
  assert.equal(app.progressPercent({ completed: -1, total: 391 }), 0);
  unmount();
});

test("every page load starts a fresh empty chat while saved chats remain accessible", async () => {
  const serverJobs = [savedRun()];
  const serverAssets = [{ id: "pm-1", role: "pm", kind: "table", name: "flight.csv", info: { rows: 3 } }];
  const first = await mountWorkspace(serverJobs, serverAssets);
  assert.notEqual(first.app.chatId.value, "f".repeat(32));
  assert.equal(first.app.selected.value.length, 0);
  assert.equal(first.app.conversation.value.length, 0);
  assert.equal(first.app.chats.value.length, 1);
  await first.app.setChat("f".repeat(32));
  assert.equal(first.app.conversation.value.length, 1);
  assert.equal(first.app.selected.value.length, 0);
  first.app.question.value = "And what does that mean?";
  await first.app.queue("analyze");
  assert.equal(serverJobs[0].request.asset_ids.length, 0);
  assert.equal(serverJobs[0].request.history[1].content, "TEST STUB: saved measurements.");
  const second = await mountWorkspace(serverJobs, serverAssets);
  assert.notEqual(second.app.chatId.value, first.app.chatId.value);
  assert.equal(second.app.conversation.value.length, 0);
  assert.equal(second.app.selected.value.length, 0);
  assert.equal(second.app.chats.value.some((c) => c.id === "f".repeat(32)), true);
});

test("explicit attachments clear after sending and resource deletion removes the selected file", async () => {
  const serverJobs = [];
  const serverAssets = [{ id: "image-1", role: "auto", kind: "raster", name: "ortho.tif", info: { width: 6000, height: 4000 } }];
  const { app } = await mountWorkspace(serverJobs, serverAssets);
  app.selected.value = ["image-1"];
  app.question.value = "Count the trucks.";
  await app.queue("analyze");
  assert.deepEqual(serverJobs[0].request.asset_ids, ["image-1"]);
  assert.equal(serverJobs[0].request.video_end, null);
  assert.equal(serverJobs[0].request.frame_count, 16);
  assert.equal(app.selected.value.length, 0);
  let opened = false;
  app.deleteDialog.value = { showModal: () => { opened = true; }, close: () => { opened = false; } };
  app.selected.value = ["image-1"];
  await app.askDelete(serverAssets[0]);
  assert.equal(opened, true);
  assert.equal(app.assets.value.length, 1);
  await app.deleteResource();
  assert.equal(app.assets.value.length, 0);
  assert.equal(app.selected.value.length, 0);
  assert.equal(opened, false);
});

test("middle-long videos may exceed one GiB while images retain their size limit", async () => {
  const { app } = await mountWorkspace([], []);
  await app.uploadFiles([{ name: "site.mp4", size: 2 * 1024 ** 3 }]);
  assert.equal(app.error.value, "");
  assert.equal(app.assets.value[0].kind, "video");
  assert.equal(app.selected.value[0], "video-upload");
  assert.equal(app.size(2 * 1024 ** 3), "2.0 GB");
  await app.uploadFiles([{ name: "too-big.mp4", size: 9 * 1024 ** 3 }]);
  assert.match(app.error.value, /8 GiB/);
  await app.uploadFiles([{ name: "too-big.png", size: 2 * 1024 ** 3 }]);
  assert.match(app.error.value, /1 GiB/);
});

test("theme follows the system initially and an explicit preference survives reload", async () => {
  const preferences = new Map();
  const first = await mountWorkspace([], [], preferences);
  assert.equal(first.app.theme.value, "dark");
  assert.equal(first.document.documentElement.dataset.theme, "dark");
  first.app.setTheme("light");
  assert.equal(preferences.get("constant-theme"), "light");
  assert.equal(first.document.documentElement.style.colorScheme, "light");
  const second = await mountWorkspace([], [], preferences);
  assert.equal(second.app.theme.value, "light");
  assert.equal(second.document.documentElement.dataset.theme, "light");
});

test("renaming and pinning update the sidebar, keep message content and survive refresh", async () => {
  const older = savedRun();
  const newer = { ...savedRun(), id: "newer", created_at: "2", request: { ...savedRun().request, chat_id: "a".repeat(32), question: "Newer question" } };
  const serverJobs = [newer, older], metadata = new Map();
  const { app } = await mountWorkspace(serverJobs, [], new Map(), metadata);
  let opened = false;
  app.renameDialog.value = { showModal: () => { opened = true; }, close: () => { opened = false; } };
  const chat = app.chats.value.find((c) => c.id === older.request.chat_id);
  await app.beginRename(chat);
  assert.equal(opened, true);
  app.renameTitle.value = "  Site safety review  ";
  await app.saveChatName();
  assert.equal(opened, false);
  assert.equal(metadata.get(chat.id).title, "Site safety review");
  assert.equal(older.request.question, "Review the earlier flight.");
  assert.equal(app.orderedChats.value[0].id, newer.request.chat_id);
  await app.toggleChatPin(app.chats.value.find((c) => c.id === chat.id));
  assert.equal(app.orderedChats.value[0].id, chat.id);
  await app.refresh();
  assert.equal(app.orderedChats.value[0].title, "Site safety review");
  assert.equal(app.orderedChats.value[0].pinned, true);
  await app.toggleChatPin(app.orderedChats.value[0]);
  assert.equal(app.orderedChats.value[0].id, newer.request.chat_id);
});

test("deleting the current chat starts a new empty chat and retains resources", async () => {
  const run = savedRun(), serverJobs = [run];
  const files = [{ id: "pm-1", role: "pm", kind: "table", name: "flight.csv", info: { rows: 3 } }];
  const { app, calls } = await mountWorkspace(serverJobs, files);
  await app.setChat(run.request.chat_id);
  let opened = false;
  app.chatDeleteDialog.value = { showModal: () => { opened = true; }, close: () => { opened = false; } };
  await app.askDeleteChat(app.chats.value[0]);
  assert.equal(opened, true);
  assert.equal(serverJobs.length, 1);
  await app.deleteChat();
  assert.equal(opened, false);
  assert.equal(app.chats.value.length, 0);
  assert.equal(app.conversation.value.length, 0);
  assert.notEqual(app.chatId.value, run.request.chat_id);
  assert.equal(app.assets.value.length, 1);
  assert.equal(calls.filter((c) => c.options.method === "DELETE").length, 1);
});

test("chat menu stays on screen and supports keyboard navigation and dismissal", async () => {
  const { app, document } = await mountWorkspace([savedRun()], []);
  let focused, restored = false;
  const items = [0, 1, 2].map((index) => ({ focus() { focused = index; document.activeElement = this; } }));
  app.chatMenuElement.value = { querySelector: () => items[0], querySelectorAll: () => items };
  const target = { getBoundingClientRect: () => ({ right: 100, bottom: 100 }), focus: () => { restored = true; } };
  await app.openChatMenu({ currentTarget: target, clientX: 1275, clientY: 715 }, app.chats.value[0]);
  assert.ok(app.chatMenu.value.x + 216 <= 1280);
  assert.ok(app.chatMenu.value.y + 150 <= 720);
  assert.equal(focused, 0);
  app.chatMenuKey({ key: "End", preventDefault() {} });
  assert.equal(focused, 2);
  app.chatMenuKey({ key: "ArrowDown", preventDefault() {} });
  assert.equal(focused, 0);
  app.chatMenuKey({ key: "Escape", preventDefault() {} });
  assert.equal(app.chatMenu.value, null);
  assert.equal(restored, true);
});

test("attachment menu offers upload and resource selection without changing selection by itself", async () => {
  const files = [{ id: "pm-1", name: "flight.csv", role: "pm", kind: "table", info: {} }];
  const { app } = await mountWorkspace([], files);
  let uploaded = false, focused = false, opened = false;
  app.attachmentMenu.value = { querySelector: () => ({ focus() { focused = true; } }) };
  app.input.value = { click() { uploaded = true; } };
  app.drawer.value = { showModal() { opened = true; } };
  await app.toggleAttachmentMenu();
  assert.equal(focused, true);
  assert.equal(app.attachmentMenuOpen.value, true);
  assert.equal(app.selected.value.length, 0);
  app.chooseUpload();
  assert.equal(uploaded, true);
  assert.equal(app.attachmentMenuOpen.value, false);
  await app.toggleAttachmentMenu();
  app.openPanel("sources");
  assert.equal(app.panel.value, "sources");
  assert.equal(opened, true);
  assert.equal(app.attachmentMenuOpen.value, false);
  app.viewSources(["pm-1"]);
  assert.equal(app.visibleAssets.value.length, 1);
  app.openPanel("sources");
  assert.equal(app.sourceScope.value, null);
});

test("adding selected resources closes the panel, focuses the composer, and never submits a message", async () => {
  const files = [
    { id: "pm-1", name: "flight.csv", role: "pm", kind: "table", info: {} },
    { id: "site-1", name: "site.png", role: "auto", kind: "image", info: {} },
  ];
  const { app, calls, document } = await mountWorkspace([], files);
  let closed = 0, focused = "";
  app.drawer.value = { showModal() {}, close() { closed++; } };
  document.querySelector = (selector) => ({ focus() { focused = selector; } });
  app.openPanel("sources");
  app.question.value = "Compare these files.";
  app.addSelectedToChat();
  assert.equal(closed, 0);
  app.selected.value = ["deleted-source"];
  app.addSelectedToChat();
  assert.equal(closed, 0);
  app.selected.value = ["pm-1"];
  app.addSelectedToChat();
  assert.equal(closed, 1);
  assert.equal(focused, "#question");
  app.openPanel("sources");
  app.selected.value = ["pm-1", "site-1"];
  const before = calls.length;
  app.addSelectedToChat();
  assert.equal(closed, 2);
  assert.deepEqual([...app.selected.value], ["pm-1", "site-1"]);
  assert.equal(app.attachments.value.length, 2);
  assert.equal(app.question.value, "Compare these files.");
  assert.equal(calls.length, before);
  app.setLanguage("uz");
  assert.equal(app.t("Add to chat"), "Suhbatga qo‘shish");
  app.setLanguage("ko");
  assert.equal(app.t("Add to chat"), "대화에 추가");
});

test("account name and role can be added, renamed and restored after refresh", async () => {
  const preferences = new Map([["constant-profile", "invalid JSON"]]);
  const first = await mountWorkspace([], [], preferences);
  assert.equal(first.app.profile.value.name, "");
  first.app.profileName.value = "  Rasul  ";
  first.app.profileRole.value = "Site engineer";
  first.app.saveProfile();
  assert.equal(first.app.profile.value.name, "Rasul");
  assert.equal(first.app.notice.value, "Profile saved.");
  const second = await mountWorkspace([], [], preferences);
  assert.equal(second.app.profile.value.name, "Rasul");
  assert.equal(second.app.profile.value.role, "Site engineer");
  second.app.profileName.value = "Research team";
  second.app.saveProfile();
  assert.equal(JSON.parse(preferences.get("constant-profile")).name, "Research team");
  second.app.profileName.value = " ";
  second.app.saveProfile();
  assert.equal(second.app.profile.value.name, "Research team");
});

test("file viewer loads actual rows and discards a slow earlier file response", async () => {
  let release;
  const files = [
    { id: "one", name: "one.csv", kind: "table", info: {} },
    { id: "two", name: "two.txt", kind: "log", info: {} },
  ];
  const contents = new Map([["one", new Promise((resolve) => { release = resolve; })],
    ["two", { kind: "log", text: "Actual file text", offset: 0, total: 16, next_offset: null }]]);
  const { app } = await mountWorkspace([], files, new Map(), new Map(), contents);
  app.drawer.value = { showModal() {} };
  const first = app.inspect(files[0]);
  await app.inspect(files[1]);
  assert.equal(app.fileContent.value.text, "Actual file text");
  release({ kind: "table", rows: [{ PM: 80 }], columns: ["PM"], total: 1 });
  await first;
  assert.equal(app.fileContent.value.kind, "log");
  assert.equal(app.fileLoading.value, false);
  await app.inspectTables({ request: { asset_ids: ["one"] } });
  assert.equal(app.fileContent.value.rows[0].PM, 80);
});

test("notifications expire independently after five seconds and clean up on unmount", async () => {
  const { app, timers, calls, unmount } = await mountWorkspace([], []);
  app.notice.value = "Files ready for your next message.";
  await nextTick();
  await nextTick();
  assert.equal(timers.size, 1);
  const [noticeId, noticeTimer] = [...timers][0];
  assert.equal(noticeTimer.delay, 5000);
  app.error.value = "Upload failed.";
  await nextTick();
  assert.equal(timers.size, 2);
  noticeTimer.fn();
  await nextTick();
  assert.equal(app.notice.value, "");
  assert.equal(app.error.value, "Upload failed.");
  assert.equal(timers.has(noticeId), false);
  app.notice.value = "A second notification.";
  await nextTick();
  const olderNoticeId = [...timers.keys()].at(-1);
  app.notice.value = "The newest notification.";
  await nextTick();
  assert.equal(timers.has(olderNoticeId), false);
  for (const timer of [...timers.values()]) timer.fn();
  await nextTick();
  await nextTick();
  assert.equal(app.notice.value, "");
  assert.equal(app.error.value, "");
  const requests = calls.length;
  app.notice.value = "Closing the app.";
  await nextTick();
  unmount();
  assert.equal(timers.size, 0);
  assert.equal(calls.length, requests);
});

test("file viewer distinguishes an outdated backend from a deleted file and can retry", async () => {
  const files = [{ id: "one", name: "one.csv", kind: "table", info: {} }];
  const path = "/api/assets/one/content?offset=0";
  const contents = new Map([[path, { ok: false, status: 404, json: async () => ({ detail: "Not Found" }) }]]);
  const { app } = await mountWorkspace([], files, new Map(), new Map(), contents);
  app.drawer.value = { showModal() {} };
  await app.inspect(files[0]);
  assert.match(app.fileError.value, /Restart FastAPI/);
  assert.equal(app.fileLoading.value, false);
  contents.set(path, { ok: false, status: 404, json: async () => ({ detail: "Record not found." }) });
  await app.loadFileContent();
  assert.match(app.fileError.value, /no longer available/);
  contents.set(path, { ok: true, json: async () => ({ kind: "table", rows: [{ PM: 12 }], total: 1, columns: ["PM"], offset: 0, next_offset: null }) });
  await app.loadFileContent();
  assert.equal(app.fileError.value, "");
  assert.equal(app.fileContent.value.rows[0].PM, 12);
});

test("a missing video route is never reported as a codec failure", async () => {
  const video = { id: "clip", name: "clip.mp4", kind: "video", info: {} };
  const path = "/api/assets/clip/media";
  const contents = new Map([[path, { ok: false, status: 404 }]]);
  const { app, calls } = await mountWorkspace([], [video], new Map(), new Map(), contents);
  app.drawer.value = { showModal() {} };
  app.inspect(video);
  await app.videoPlaybackError("clip");
  assert.match(app.videoError.value, /Restart FastAPI/);
  assert.doesNotMatch(app.videoError.value, /decode|codec/);
  assert.equal(calls.at(-1).options.method, "HEAD");
  contents.set(path, { ok: true, status: 200 });
  await app.videoPlaybackError("clip");
  assert.match(app.videoError.value, /cannot decode/);
});

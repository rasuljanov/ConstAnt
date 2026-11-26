<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { cleanAnswer, renderMarkdown } from "./markdown.js";
import { LANGUAGES, messageTime, responseDuration, translate } from "./locale.js";
import Icon from "./Icon.vue";

const assets = ref([]),
  jobs = ref([]),
  chats = ref([]),
  health = ref(null),
  selected = ref([]);
const question = ref(""),
  error = ref(""),
  notice = ref("");
const uploading = ref(false),
  progress = ref(0),
  uploadName = ref(""),
  submitting = ref(false);
const input = ref(null),
  drawer = ref(null),
  deleteDialog = ref(null),
  chatEnd = ref(null);
const panel = ref("sources"),
  search = ref(""),
  filter = ref("all"),
  inspectedId = ref("");
const chatId = ref(crypto.randomUUID().replaceAll("-", ""));
const profile = ref(readProfile()), profileName = ref(profile.value.name), profileRole = ref(profile.value.role), profileStatus = ref("");
const attachmentMenuOpen = ref(false), attachmentMenu = ref(null), sourceScope = ref(null);
const fileContent = ref(null), fileLoading = ref(false), fileError = ref(""), videoError = ref("");
const notificationHost = ref(null);
const language = ref(LANGUAGES.some((l) => l.code === localStorage.getItem("constant-language")) ? localStorage.getItem("constant-language") : "en");
const copiedMessage = ref("");
let copyTimer;
const t = (text) => translate(language.value, text);
let inspectionRequest = 0;
const savedTheme = localStorage.getItem("constant-theme");
const theme = ref(["light", "dark"].includes(savedTheme) ? savedTheme :
  (typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
const chatMenu = ref(null), chatMenuElement = ref(null), renameDialog = ref(null), chatDeleteDialog = ref(null);
const editingChat = ref(null), renameTitle = ref(""), deletingChat = ref(null), chatSaving = ref(false), chatError = ref("");
let chatMenuAnchor;
const sidebarOpen = ref(false), loadingChat = ref(false), deleteTarget = ref(null), deleting = ref(false), deleteError = ref("");
const imageEdge = ref(768),
  tileEdge = ref(1024),
  frameCount = ref(16),
  videoStart = ref(0),
  videoEnd = ref(""),
  outputTokens = ref(768);
const crop = ref({ x: 0, y: 0, width: 1024, height: 1024 }),
  bandText = ref("");
const savingCrop = ref(false),
  previewFailed = ref(false),
  reportBusy = ref(false);
let timer,
  stopped = false;

const model = computed(() => health.value?.model);
const activeJobs = computed(() =>
  jobs.value.filter((j) => ["queued", "running"].includes(j.status)),
);
const pendingUpdates = computed(() => jobs.value.filter((j) => ["queued", "running"].includes(j.status) || j.title_pending));
const analyses = computed(() =>
  jobs.value.filter((j) => j.request.action === "analyze"),
);
const conversation = computed(() =>
  analyses.value
    .filter((j) => (j.request.chat_id || "legacy") === chatId.value)
    .sort((a, b) => a.created_at.localeCompare(b.created_at)),
);
const chatBusy = computed(() =>
  conversation.value.some((j) => ["queued", "running"].includes(j.status)),
);
const pendingRun = computed(() => conversation.value.find((j) => ["queued", "running"].includes(j.status)));
const selectedAssets = computed(() =>
  assets.value.filter((a) => selected.value.includes(a.id)),
);
const pmAssets = computed(() =>
  assets.value.filter(
    (a) => a.role === "pm" && !a.name.startsWith("SYNTHETIC"),
  ),
);
const pmSelected = computed(
  () =>
    pmAssets.value.length > 0 &&
    pmAssets.value.every((a) => selected.value.includes(a.id)),
);
const hasVideo = computed(() =>
  selectedAssets.value.some((a) => a.kind === "video"),
);
const attachments = computed(() => selectedAssets.value);
const focused = computed(() =>
  assets.value.find((a) => a.id === inspectedId.value),
);
const visibleAssets = computed(() =>
  assets.value.filter((a) => {
    const category =
      a.role === "pm"
        ? "pm"
        : ["raster", "image"].includes(a.kind)
          ? "images"
          : a.kind === "video"
            ? "videos"
            : "other";
    return (
      (!sourceScope.value || sourceScope.value.includes(a.id)) &&
      (filter.value === "all" || category === filter.value) &&
      a.name.toLowerCase().includes(search.value.toLowerCase())
    );
  }),
);
const chatTitle = (chat) => chat?.title || t("New chat");
const currentTitle = computed(() => chatTitle(chats.value.find((c) => c.id === chatId.value)));
const orderedChats = computed(() => [...chats.value].sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned) || b.updated_at.localeCompare(a.updated_at)));
const previewUrl = computed(() =>
  focused.value
    ? "/api/assets/" +
      focused.value.id +
      "/preview" +
      (focused.value.kind === "raster" && bandText.value
        ? "?bands=" + encodeURIComponent(bandText.value)
        : "")
    : "",
);
const selectionBox = computed(() => {
  const info = focused.value?.info;
  return info
    ? {
        left: (crop.value.x / info.width) * 100 + "%",
        top: (crop.value.y / info.height) * 100 + "%",
        width: (crop.value.width / info.width) * 100 + "%",
        height: (crop.value.height / info.height) * 100 + "%",
      }
    : {};
});
function errorText(detail) {
  return Array.isArray(detail)
    ? detail.map((e) => e.msg).join("; ")
    : typeof detail === "string"
      ? detail
      : JSON.stringify(detail);
}
async function api(path, options = {}) {
  const response = await fetch("/api" + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const failure = new Error(errorText(body.detail || "Request failed (" + response.status + ")"));
    failure.status = response.status;
    throw failure;
  }
  return response.json();
}
function post(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
function usable(a) {
  return !["model", "geometry"].includes(a.kind);
}
function number(value) {
  return value == null
    ? "—"
    : Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
}
function size(value) {
  return value >= 1024 ** 3
    ? (value / 1024 ** 3).toFixed(1) + " GB"
    : value >= 1024 ** 2
    ? (value / 1024 ** 2).toFixed(1) + " MB"
    : (value / 1024).toFixed(1) + " KB";
}
function sourceName(id) {
  return assets.value.find((a) => a.id === id)?.name || id.slice(0, 8);
}

async function refresh() {
  try {
    const [h, a, j, c] = await Promise.all([
      api("/health"),
      api("/assets"),
      api("/jobs"),
      api("/chats"),
    ]);
    if (stopped) return;
    health.value = h;
    assets.value = a;
    jobs.value = j;
    chats.value = c;
    selected.value = selected.value.filter((id) => a.some((item) => item.id === id));
  } catch (e) {
    if (!stopped) {
      health.value = null;
      error.value = e.message + " · Check that FastAPI is running.";
    }
  }
}
async function poll() {
  if (stopped || !pendingUpdates.value.length) return;
  try {
    const updated = await api("/jobs");
    if (!stopped) {
      const pending = pendingUpdates.value;
      const finished = updated
        .filter((job) => job.model && job.finished_at && pending.some((p) => p.id === job.id))
        .sort((a, b) => b.finished_at.localeCompare(a.finished_at))[0];
      if (finished) health.value = { ...health.value, model: finished.model };
      if (pending.some((p) => updated.some((j) => j.id === p.id && !["queued", "running"].includes(j.status))))
        chats.value = await api("/chats");
      jobs.value = [
        ...pending.filter((job) => !updated.some((j) => j.id === job.id)),
        ...updated,
      ];
    }
  } catch (e) {
    if (!stopped) error.value = e.message + " · Could not refresh job status.";
  }
  if (!stopped && pendingUpdates.value.length) timer = setTimeout(poll, 2500);
}
watch(
  () => pendingUpdates.value.length > 0,
  (active) => {
    clearTimeout(timer);
    if (active && !stopped) timer = setTimeout(poll, 2500);
  },
);
watch(
  () =>
    conversation.value.map((j) => j.id + j.status + (j.answer || "")).join(""),
  async () => {
    await nextTick();
    chatEnd.value?.scrollIntoView({ behavior: "smooth", block: "end" });
  },
);
const stopNotifications = [error, notice].map((message) => watch(message, (text, previous, cleanup) => {
  if (!text) return;
  const timeout = setTimeout(() => { message.value = ""; }, 5000);
  cleanup(() => clearTimeout(timeout));
}));
async function setChat(id) {
  chatId.value = id;
  selected.value = [];
  error.value = "";
  notice.value = "";
  question.value = "";
  drawer.value?.close();
  sidebarOpen.value = false;
  loadingChat.value = true;
  try {
    const saved = await api("/jobs?chat_id=" + encodeURIComponent(id));
    jobs.value = [...jobs.value.filter((j) => (j.request.chat_id || "legacy") !== id), ...saved];
  } catch (e) { error.value = e.message; }
  finally { if (chatId.value === id) loadingChat.value = false; }
}
function newChat() {
  closeChatMenu(false);
  attachmentMenuOpen.value = false;
  chatId.value = crypto.randomUUID().replaceAll("-", "");
  selected.value = [];
  question.value = "";
  error.value = "";
  notice.value = "";
  loadingChat.value = false;
  sidebarOpen.value = false;
  drawer.value?.close();
}
function openPanel(name) {
  attachmentMenuOpen.value = false;
  sidebarOpen.value = false;
  if (name === "sources") sourceScope.value = null;
  panel.value = name;
  drawer.value.showModal();
  notificationHost.value = drawer.value;
}
function viewSources(ids) {
  openPanel("sources");
  search.value = "";
  filter.value = "all";
  sourceScope.value = ids;
}
function inspectTables(run) {
  const tables = assets.value.filter((a) => a.kind === "table" && run.request.asset_ids.includes(a.id));
  if (tables.length === 1) return inspect(tables[0]);
  viewSources(tables.map((a) => a.id));
}
function inspect(a) {
  inspectionRequest++;
  fileContent.value = null;
  fileError.value = "";
  videoError.value = "";
  fileLoading.value = false;
  inspectedId.value = a.id;
  bandText.value = "";
  previewFailed.value = false;
  crop.value = {
    x: 0,
    y: 0,
    width: Math.min(1024, a.info.width || 1024),
    height: Math.min(1024, a.info.height || 1024),
  };
  openPanel("inspect");
  if (["table", "log"].includes(a.kind)) return loadFileContent();
}
async function loadFileContent(offset = 0) {
  const id = inspectedId.value, request = ++inspectionRequest;
  fileLoading.value = true;
  fileError.value = "";
  try {
    const content = await api("/assets/" + id + "/content?offset=" + offset);
    if (request === inspectionRequest && id === inspectedId.value) fileContent.value = content;
  } catch (e) {
    if (request === inspectionRequest) fileError.value = viewerError(e);
  } finally {
    if (request === inspectionRequest) fileLoading.value = false;
  }
}
function viewerError(failure) {
  if (failure.status === 404) return failure.message === "Not Found"
    ? "The running backend needs an update. Restart FastAPI, then retry opening this file."
    : "This file is no longer available. Refresh resources and choose it again.";
  return failure.message;
}
async function videoPlaybackError(id) {
  try {
    const response = await fetch("/api/assets/" + id + "/media", { method: "HEAD" });
    if (id !== inspectedId.value) return;
    if (!response.ok) {
      const failure = new Error(response.status === 404 ? "Not Found" : "Video request failed (" + response.status + ").");
      failure.status = response.status;
      videoError.value = viewerError(failure);
    } else videoError.value = "This browser cannot decode this video. Download the original below to use a compatible player.";
  } catch {
    if (id === inspectedId.value) videoError.value = "The video server could not be reached. Check FastAPI and try reopening the file.";
  }
}
async function toggleAttachmentMenu() {
  attachmentMenuOpen.value = !attachmentMenuOpen.value;
  await nextTick();
  attachmentMenu.value?.querySelector('[role="menuitem"]')?.focus();
}
function closeAttachmentMenu() {
  attachmentMenuOpen.value = false;
}
function attachmentMenuKey(event) {
  if (event.key === "Escape") { event.preventDefault(); closeAttachmentMenu(); document.querySelector('.attach-button')?.focus(); }
  if (event.key === "Tab") closeAttachmentMenu();
  if (["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    const items = [...attachmentMenu.value.querySelectorAll('button')];
    const current = items.indexOf(document.activeElement);
    items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (current + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length]?.focus();
  }
}
function chooseUpload() {
  closeAttachmentMenu();
  input.value.click();
}
function readProfile() {
  try {
    const stored = JSON.parse(localStorage.getItem("constant-profile") || "{}");
    return { name: typeof stored?.name === "string" ? stored.name.slice(0, 80) : "", role: typeof stored?.role === "string" ? stored.role.slice(0, 80) : "" };
  } catch { return { name: "", role: "" }; }
}
function saveProfile() {
  if (!profileName.value.trim()) { profileStatus.value = "Enter your name."; return; }
  const updated = { name: profileName.value.trim().slice(0, 80), role: profileRole.value.trim().slice(0, 80) };
  try {
    localStorage.setItem("constant-profile", JSON.stringify(updated));
    profile.value = updated;
    profileStatus.value = "";
    notice.value = "Profile saved.";
  } catch { profileStatus.value = "Could not save the profile in this browser."; }
}
function toggle(a) {
  if (selected.value.includes(a.id))
    selected.value = selected.value.filter((id) => id !== a.id);
  else if (selected.value.length < 40) selected.value.push(a.id);
  else error.value = "Select at most 40 sources per message.";
}
function addSelectedToChat() {
  if (!attachments.value.length) return;
  drawer.value.close();
  document.querySelector("#question")?.focus();
}
function togglePM() {
  if (pmSelected.value)
    selected.value = selected.value.filter(
      (id) => !pmAssets.value.some((p) => p.id === id),
    );
  else {
    const next = Array.from(
      new Set([...selected.value, ...pmAssets.value.map((p) => p.id)]),
    );
    if (next.length > 40) {
      error.value = "Select at most 40 sources per message.";
      return;
    }
    selected.value = next;
  }
}
async function uploadFiles(files) {
  if (uploading.value) return;
  uploading.value = true;
  error.value = "";
  notice.value = "";
  try {
    for (const file of files) {
      const video = /\.(mp4|mov|avi|mkv)$/i.test(file.name);
      if (file.size > (video ? 8 : 1) * 1024 ** 3)
        throw new Error(video ? "Videos must be 8 GiB or smaller." : "Images and other files must be 1 GiB or smaller.");
      uploadName.value = file.name;
      progress.value = 0;
      const item = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest(),
          body = new FormData();
        body.append("file", file);
        body.append(
          "role",
          file.name.toLowerCase().endsWith(".csv") ? "pm" : "auto",
        );
        xhr.open("POST", "/api/assets");
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable)
            progress.value = Math.round((event.loaded / event.total) * 100);
        };
        xhr.onerror = () =>
          reject(new Error("Upload connection failed. Check the backend."));
        xhr.onload = () => {
          let data;
          try {
            data = JSON.parse(xhr.responseText);
          } catch {
            reject(new Error("Upload failed: invalid server response."));
            return;
          }
          if (xhr.status >= 200 && xhr.status < 300) resolve(data);
          else
            reject(
              new Error(
                errorText(data.detail || "Upload failed (" + xhr.status + ")"),
              ),
            );
        };
        xhr.send(body);
      });
      assets.value.unshift(item);
      if (usable(item) && selected.value.length < 40)
        selected.value.push(item.id);
    }
    notice.value =
      "Files ready for your next message.";
  } catch (e) {
    error.value = e.message;
  } finally {
    uploading.value = false;
    if (input.value) input.value.value = "";
  }
}
function pickCrop(event) {
  if (focused.value?.kind !== "raster") return;
  const box = event.currentTarget.getBoundingClientRect(),
    info = focused.value.info;
  crop.value.x = Math.max(
    0,
    Math.min(
      info.width - crop.value.width,
      Math.round(
        ((event.clientX - box.left) / box.width) * info.width -
          crop.value.width / 2,
      ),
    ),
  );
  crop.value.y = Math.max(
    0,
    Math.min(
      info.height - crop.value.height,
      Math.round(
        ((event.clientY - box.top) / box.height) * info.height -
          crop.value.height / 2,
      ),
    ),
  );
}
async function saveCrop() {
  savingCrop.value = true;
  error.value = "";
  try {
    const parent = focused.value.id;
    const bands = bandText.value.trim()
      ? bandText.value.split(",").map((n) => Number(n.trim()))
      : null;
    const item = await post("/assets/" + parent + "/crops", {
      ...crop.value,
      bands,
    });
    assets.value.unshift(item);
    selected.value = selected.value.filter((id) => id !== parent);
    if (selected.value.length < 40) selected.value.push(item.id);
    drawer.value.close();
    notice.value =
      "Crop attached. Its original pixel window and geographic bounds are preserved.";
  } catch (e) {
    error.value = e.message;
  } finally {
    savingCrop.value = false;
  }
}
async function queue(action) {
  submitting.value = true;
  error.value = "";
  notice.value = "";
  const asked = question.value,
    currentChat = chatId.value;
  try {
    const history = conversation.value
      .filter((j) => j.status === "completed" && j.answer)
      .flatMap((j) => [
        { role: "user", content: j.request.question },
        { role: "assistant", content: j.answer },
      ])
      .slice(-6)
      .map((turn) => ({ ...turn, content: turn.content.slice(0, 6000) }));
    const job = await post("/jobs", {
      action,
      chat_id: currentChat,
      history: action === "analyze" ? history : [],
      asset_ids: action === "analyze" ? [...selected.value] : [],
      question: asked,
      language: language.value,
      image_edge: Number(imageEdge.value),
      tile_edge: Number(tileEdge.value),
      frame_count: Number(frameCount.value),
      video_start: Number(videoStart.value),
      video_end: videoEnd.value === "" ? null : Number(videoEnd.value),
      max_new_tokens: Number(outputTokens.value),
    });
    jobs.value.unshift(job);
    if (action === "analyze") {
      if (!chats.value.some((c) => c.id === currentChat))
        chats.value.unshift({ id: currentChat, title: null, updated_at: job.created_at });
      if (chatId.value === currentChat) selected.value = [];
    }
    if (
      action === "analyze" &&
      question.value === asked &&
      chatId.value === currentChat
    )
      question.value = "";
    if (action !== "analyze") notice.value = "Model " + action + " queued.";
  } catch (e) {
    error.value = e.message;
  } finally {
    submitting.value = false;
  }
}
function send() {
  if (
    !question.value.trim() ||
    chatBusy.value ||
    submitting.value ||
    !health.value ||
    activeJobs.value.length >= 3
  )
    return;
  queue("analyze");
}
function composerKey(event) {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    send();
  }
}
async function exportReport() {
  reportBusy.value = true;
  error.value = "";
  try {
    const complete = conversation.value.filter(
      (r) => r.status === "completed" && r.answer,
    );
    const sourceIds = Array.from(
      new Set([
        ...selected.value,
        ...complete.flatMap((r) => r.effective_asset_ids || r.request.asset_ids),
      ]),
    );
    if (!sourceIds.length)
      throw new Error(
        "Attach at least one source before exporting an evidence report.",
      );
    const response = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        asset_ids: sourceIds,
        run_ids: complete.map((r) => r.id),
      }),
    });
    if (!response.ok) {
      const body = await response.json();
      throw new Error(errorText(body.detail));
    }
    const url = URL.createObjectURL(await response.blob()),
      link = document.createElement("a");
    link.href = url;
    link.download = "construction-chat-report.md";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    error.value = e.message;
  } finally {
    reportBusy.value = false;
  }
}
function resourceBusy(id) {
  return activeJobs.value.some((j) => (j.effective_asset_ids || j.request.asset_ids).includes(id));
}
async function askDelete(item) {
  deleteTarget.value = item;
  deleteError.value = "";
  await nextTick();
  deleteDialog.value.showModal();
}
async function deleteResource() {
  deleting.value = true;
  deleteError.value = "";
  try {
    const id = deleteTarget.value.id;
    await api("/assets/" + id, { method: "DELETE" });
    assets.value = assets.value.filter((a) => a.id !== id);
    selected.value = selected.value.filter((a) => a !== id);
    if (inspectedId.value === id) panel.value = "sources";
    deleteDialog.value.close();
    deleteTarget.value = null;
    notice.value = "File deleted. Saved chat answers remain available.";
  } catch (e) { deleteError.value = e.message; }
  finally { deleting.value = false; }
}
async function stopJob(run) {
  if (!run || run.cancel_requested) return;
  run.cancel_requested = true;
  try {
    await post("/jobs/" + run.id + "/cancel", {});
  } catch (e) { run.cancel_requested = false; error.value = e.message; }
}
function setLanguage(value) {
  if (!LANGUAGES.some((l) => l.code === value)) return;
  language.value = value;
  document.documentElement.lang = value;
  try { localStorage.setItem("constant-language", value); }
  catch { /* The selected language still applies for this page. */ }
}
function thinkingText(run) {
  if (run.cancel_requested) return t("Stopping…");
  if (run.status === "queued") return t("Waiting for the GPU…");
  return run.progress ? `${t("Analyzing views")} · ${run.progress.completed} / ${run.progress.total}` : t("Thinking…");
}
function progressPercent(progress) {
  if (!progress?.total) return 0;
  return Math.min(100, Math.max(0, progress.completed / progress.total * 100));
}
async function copyMessage(run, side = "response") {
  try {
    await navigator.clipboard.writeText(side === "request" ? run.request.question : cleanAnswer(run.answer));
    copiedMessage.value = run.id + ":" + side;
    clearTimeout(copyTimer);
    copyTimer = setTimeout(() => { copiedMessage.value = ""; }, 2000);
  } catch { error.value = t("Could not copy this message. Select the text and copy it manually."); }
}
function setTheme(value) {
  theme.value = value;
  localStorage.setItem("constant-theme", value);
  document.documentElement.dataset.theme = value;
  document.documentElement.style.colorScheme = value;
}
function closeChatMenu(restoreFocus = true) {
  chatMenu.value = null;
  if (restoreFocus) chatMenuAnchor?.focus();
}
async function openChatMenu(event, chat) {
  const box = event.currentTarget.getBoundingClientRect();
  chatMenuAnchor = event.currentTarget.querySelector?.('.chat-link') || event.currentTarget;
  chatMenu.value = { chat, x: Math.max(8, Math.min(event.clientX || box.right, window.innerWidth - 224)),
    y: Math.max(8, Math.min(event.clientY || box.bottom, window.innerHeight - 160)) };
  await nextTick();
  chatMenuElement.value?.querySelector('[role="menuitem"]')?.focus();
}
function chatIsActive(id) {
  return activeJobs.value.some((j) => (j.request.chat_id || "legacy") === id);
}
function chatMenuKey(event) {
  if (event.key === "Escape") { event.preventDefault(); closeChatMenu(); return; }
  if (event.key === "Tab") { closeChatMenu(); return; }
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const items = [...chatMenuElement.value.querySelectorAll('button:not(:disabled)')];
  const current = items.indexOf(document.activeElement);
  const index = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 :
    (current + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length;
  items[index]?.focus();
}
function applyChatUpdate(updated) {
  chats.value = chats.value.map((c) => c.id === updated.id ? updated : c);
}
async function beginRename(chat) {
  editingChat.value = chat;
  renameTitle.value = chatTitle(chat);
  chatError.value = "";
  closeChatMenu(false);
  await nextTick();
  renameDialog.value.showModal();
}
async function saveChatName() {
  if (!renameTitle.value.trim() || chatSaving.value) return;
  chatSaving.value = true;
  chatError.value = "";
  try {
    applyChatUpdate(await api("/chats/" + editingChat.value.id, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: renameTitle.value.trim() }),
    }));
    renameDialog.value.close();
    editingChat.value = null;
  } catch (e) { chatError.value = e.message; }
  finally { chatSaving.value = false; }
}
async function toggleChatPin(chat) {
  if (chatSaving.value) return;
  closeChatMenu();
  chatSaving.value = true;
  try {
    applyChatUpdate(await api("/chats/" + chat.id, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pinned: !chat.pinned }),
    }));
  } catch (e) { error.value = e.message; }
  finally { chatSaving.value = false; }
}
async function askDeleteChat(chat) {
  deletingChat.value = chat;
  chatError.value = "";
  closeChatMenu(false);
  await nextTick();
  chatDeleteDialog.value.showModal();
}
async function deleteChat() {
  chatSaving.value = true;
  chatError.value = "";
  try {
    const id = deletingChat.value.id;
    await api("/chats/" + id, { method: "DELETE" });
    chats.value = chats.value.filter((c) => c.id !== id);
    jobs.value = jobs.value.filter((j) => (j.request.chat_id || "legacy") !== id);
    chatDeleteDialog.value.close();
    deletingChat.value = null;
    if (chatId.value === id) newChat();
  } catch (e) { chatError.value = e.message; }
  finally { chatSaving.value = false; }
}
onMounted(async () => {
  document.documentElement.dataset.theme = theme.value;
  document.documentElement.style.colorScheme = theme.value;
  document.documentElement.lang = language.value;
  await refresh();
});
onUnmounted(() => {
  stopped = true;
  clearTimeout(timer);
  clearTimeout(copyTimer);
  stopNotifications.forEach((stop) => stop());
});
</script>

<template>
  <div
    class="chat-app"
    @dragover.prevent
    @drop.prevent="uploadFiles($event.dataTransfer.files)"
  >
    <Teleport :to="notificationHost || 'body'">
    <div v-if="error || notice" class="notification-stack" role="region" aria-label="Notifications">
      <div v-if="error" class="toast error" role="alert"><Icon name="info" :size="18" /><span>{{ error }}</span><button class="icon-button" aria-label="Dismiss error" @click="error = ''"><Icon name="close" :size="16" /></button></div>
      <div v-if="notice" class="toast notice" role="status"><Icon name="check" :size="18" /><span>{{ notice }}</span><button class="icon-button" aria-label="Dismiss notice" @click="notice = ''"><Icon name="close" :size="16" /></button></div>
    </div>
    </Teleport>
    <button v-if="sidebarOpen" class="sidebar-backdrop" aria-label="Close sidebar" @click="sidebarOpen = false"></button>
    <aside class="chat-sidebar" :class="{ open: sidebarOpen }" aria-label="Chat history">
      <a href="/" class="brand" aria-label="ConstAnt home"><span class="brand-logo"><img src="/constant-logo.png" alt="" /></span><span>ConstAnt</span></a>
      <button class="sidebar-new" @click="newChat"><Icon name="plus" :size="18" /> {{ t('New chat') }}</button>
      <p class="sidebar-label">{{ t('Chats') }}</p>
      <nav class="chat-history" aria-label="Saved chats">
        <div v-for="chat in orderedChats" :key="chat.id" class="chat-history-row" :class="{ active: chat.id === chatId }" @contextmenu.prevent="openChatMenu($event, chat)">
          <button class="chat-link" :title="chatTitle(chat)" :aria-label="(chat.pinned ? 'Pinned: ' : '') + chatTitle(chat)" @click="setChat(chat.id)">
            <span class="history-dot" v-if="chatIsActive(chat.id)"></span><Icon v-else-if="chat.pinned" name="pin" :size="13" class="pin-indicator" /><span>{{ chatTitle(chat) }}</span>
          </button>
          <button class="icon-button chat-more" :aria-label="'Chat actions for ' + chatTitle(chat)" @click.stop="openChatMenu($event, chat)"><Icon name="more" :size="17" /></button>
        </div>
        <p v-if="!chats.length" class="sidebar-empty">{{ t('Your chats will be saved here.') }}</p>
      </nav>
      <div class="sidebar-bottom"><button class="sidebar-settings" @click="openPanel('settings')"><Icon name="settings" :size="18" /> {{ t('Settings') }}</button><button class="icon-button theme-toggle" :aria-label="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'" :title="theme === 'dark' ? 'Light mode' : 'Dark mode'" @click="setTheme(theme === 'dark' ? 'light' : 'dark')"><Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" /></button></div>
    </aside>
    <template v-if="chatMenu">
      <div class="chat-menu-backdrop" @click="closeChatMenu()" @contextmenu.prevent="closeChatMenu()"></div>
      <div ref="chatMenuElement" class="chat-context-menu" role="menu" aria-label="Chat actions" :style="{ left: chatMenu.x + 'px', top: chatMenu.y + 'px' }" @keydown="chatMenuKey">
        <button role="menuitem" :disabled="chatSaving" @click="beginRename(chatMenu.chat)"><Icon name="edit" :size="17" /> {{ t('Rename') }}</button>
        <button role="menuitem" :disabled="chatSaving" @click="toggleChatPin(chatMenu.chat)"><Icon :name="chatMenu.chat.pinned ? 'unpin' : 'pin'" :size="17" /> {{ t(chatMenu.chat.pinned ? 'Unpin chat' : 'Pin chat') }}</button>
        <button role="menuitem" class="menu-danger" :disabled="chatSaving || chatIsActive(chatMenu.chat.id)" :title="chatIsActive(chatMenu.chat.id) ? 'Stop the active analysis before deleting this chat' : ''" @click="askDeleteChat(chatMenu.chat)"><Icon name="trash" :size="17" /> {{ t('Delete chat') }}</button>
      </div>
    </template>
    <div class="workspace">
    <header class="app-header">
      <button class="icon-button sidebar-toggle" :aria-label="t('Open sidebar')" @click="sidebarOpen = true"><Icon name="menu" /></button>
      <span class="chat-title">{{ currentTitle }}</span>
      <nav aria-label="Workspace actions">
        <label class="language-picker header-control" :title="t('Language')">
          <Icon name="globe" :size="18" />
          <select :value="language" :aria-label="t('Language')" @change="setLanguage($event.target.value)">
            <option v-for="item in LANGUAGES" :key="item.code" :value="item.code">{{ item.label }}</option>
          </select>
          <Icon name="chevron" :size="13" />
        </label>
        <button class="icon-button resources-button header-control" :aria-label="t('Open resources')" :title="t('Resources')" @click="openPanel('sources')">
          <Icon name="resources" :size="18" />
        </button>
        <button
          class="icon-button account-button header-control"
          :aria-label="t('Open account')"
          :title="profile.name ? t('Account') + ' · ' + profile.name : t('Account')"
          @click="openPanel('account')"
        >
          <span v-if="profile.name" class="profile-initial">{{ profile.name[0].toUpperCase() }}</span><Icon v-else name="account" :size="18" />
        </button>
      </nav>
    </header>

    <main class="chat-main" :class="{ 'has-messages': conversation.length }">
      <p v-if="loadingChat" class="loading-chat">{{ t('Loading chat…') }}</p>
      <section v-else-if="!conversation.length" class="welcome">
        <h1>{{ t('What would you like to know?') }}</h1>
        <p class="welcome-copy">
          {{ t('Ask about your site using imagery, video, measurements, or the conversation so far.') }}
        </p>
      </section>

      <section
        v-else
        class="thread"
        aria-label="Conversation"
        aria-live="polite"
      >
        <article v-for="run in conversation" :key="run.id" class="chat-turn">
          <div class="user-message">
            <p>{{ run.request.question }}</p>
            <span v-if="run.context_asset_ids?.length" class="context-note">{{ t(run.reused_visual_run_id ? 'Using the previous scan' : 'Using earlier files in this chat') }}</span>
            <div v-if="run.request.asset_ids.length" class="message-sources">
              <button
                v-for="id in run.request.asset_ids.filter(
                  (id) => assets.find((a) => a.id === id)?.kind !== 'table',
                )"
                :key="id"
                @click="
                  assets.find((a) => a.id === id) &&
                  inspect(assets.find((a) => a.id === id))
                "
              >
                <Icon :name="assets.find((a) => a.id === id)?.kind === 'video' ? 'video' : ['image', 'raster'].includes(assets.find((a) => a.id === id)?.kind) ? 'image' : 'file'" :size="13" /> {{ sourceName(id) }}</button
              ><button
                v-if="
                  run.request.asset_ids.some(
                    (id) => assets.find((a) => a.id === id)?.kind === 'table',
                  )
                "
                @click="inspectTables(run)"
                ><Icon name="table" :size="13" />
                {{
                  run.request.asset_ids.filter(
                    (id) => assets.find((a) => a.id === id)?.kind === "table",
                  ).length
                }}
                {{ t('table sources') }}</button
              >
            </div>
          </div>
          <div class="request-footer">
            <time v-if="messageTime(run.created_at, language)" :datetime="run.created_at">{{ messageTime(run.created_at, language) }}</time>
            <button class="icon-button copy-button" :aria-label="t(copiedMessage === run.id + ':request' ? 'Copied' : 'Copy request')" :title="t(copiedMessage === run.id + ':request' ? 'Copied' : 'Copy request')" @click="copyMessage(run, 'request')"><Icon :name="copiedMessage === run.id + ':request' ? 'check' : 'copy'" :size="16" /></button>
          </div>
          <div class="assistant-message">
            <span class="assistant-avatar"><img src="/constant-logo.png" alt="" /></span>
            <div class="assistant-content">
              <div class="assistant-name">ConstAnt</div>
              <div
                v-if="['queued', 'running'].includes(run.status)"
                class="thinking"
              >
                <span v-if="!run.progress" class="ant-loader" aria-hidden="true">
                  <span class="ant-footsteps"><i></i><i></i><i></i></span><Icon name="ant" :size="20" />
                </span>
                {{ thinkingText(run) }}
              </div>
              <p v-if="run.error" class="response-error">{{ run.error }}</p>
              <div v-if="run.progress" class="scan-progress">
                <div class="scan-track">
                  <progress :value="run.progress.completed" :max="run.progress.total || 1" aria-label="Analysis coverage"></progress>
                  <Icon v-if="run.status === 'running' && !run.cancel_requested && run.progress.total > 0" name="ant" class="progress-ant" :size="18" :style="{ left: progressPercent(run.progress) + '%' }" />
                </div>
                <div><span>{{ run.progress.completed }} / {{ run.progress.total }} {{ t('views processed') }}</span></div>
                <p v-if="run.progress.failed" class="response-warning">{{ run.progress.failed }} views could not be interpreted. Counts are incomplete.</p>
              </div>
              <div
                v-if="run.answer"
                class="answer"
                v-html="renderMarkdown(run.answer)"
              ></div>
              <p v-if="run.metrics?.truncated" class="response-warning">
                The response reached its output limit. Increase output tokens
                for a longer answer.
              </p>
              <div
                v-if="['completed', 'failed', 'cancelled'].includes(run.status)"
                class="response-footer"
              >
                <time v-if="messageTime(run.finished_at || run.created_at, language)" :datetime="run.finished_at || run.created_at">{{ messageTime(run.finished_at || run.created_at, language) }}</time>
                <button v-if="run.answer" class="icon-button copy-button" :aria-label="t(copiedMessage === run.id + ':response' ? 'Copied' : 'Copy response')" :title="t(copiedMessage === run.id + ':response' ? 'Copied' : 'Copy response')" @click="copyMessage(run)"><Icon :name="copiedMessage === run.id + ':response' ? 'check' : 'copy'" :size="16" /></button>
                <span v-if="responseDuration(run, language)" class="elapsed-time">{{ responseDuration(run, language) }}</span>
                <a class="icon-button" :href="'/api/jobs/' + run.id + '/export'" :aria-label="t('Run details')" :title="t('Run details')"><Icon name="download" :size="16" /></a>
              </div>
            </div>
          </div>
        </article>
        <div ref="chatEnd"></div>
      </section>
    </main>

    <section class="composer-dock" aria-label="Message composer">
      <div class="composer" :class="{ busy: chatBusy }">
        <div v-if="attachments.length" class="context-bar">
          <span v-for="a in attachments" :key="a.id" class="context-chip selected">
            <button :title="a.name" @click="inspect(a)"><Icon :name="a.kind === 'video' ? 'video' : a.kind === 'table' ? 'table' : ['image', 'raster'].includes(a.kind) ? 'image' : 'file'" :size="14" /><span>{{ a.name }}</span></button>
            <button :aria-label="'Detach ' + a.name" @click="toggle(a)"><Icon name="close" :size="14" /></button>
          </span>
        </div>
        <div class="composer-row">
          <div class="attachment-control">
            <button class="attach-button" :aria-label="t('Add attachment')" :title="t('Add attachment')" aria-haspopup="menu" :aria-expanded="attachmentMenuOpen" :disabled="uploading" @click="toggleAttachmentMenu"><Icon name="plus" :size="22" /></button>
            <template v-if="attachmentMenuOpen">
              <div class="attachment-backdrop" @click="closeAttachmentMenu"></div>
              <div ref="attachmentMenu" class="attachment-menu" role="menu" :aria-label="t('Add attachment')" @keydown="attachmentMenuKey">
                <button role="menuitem" @click="chooseUpload"><Icon name="upload" :size="18" /> {{ t('Upload files') }}</button>
                <button role="menuitem" @click="openPanel('sources')"><Icon name="resources" :size="18" /> {{ t('Add from resources') }}</button>
              </div>
            </template>
            <input ref="input" class="visually-hidden" type="file" multiple accept=".csv,.tsv,.txt,.log,.json,.jsonl,.tif,.tiff,.png,.jpg,.jpeg,.mp4,.mov,.avi,.mkv,.joblib,.las,.laz,.ply,.obj,.xyz,.pcd,.glb,.gltf" @change="uploadFiles($event.target.files)" />
          </div>
          <label class="visually-hidden" for="question">{{ t('Message ConstAnt') }}</label>
          <textarea id="question" v-model="question" rows="1" maxlength="4000" :placeholder="t('Ask ConstAnt')" @keydown="composerKey"></textarea>
          <button class="send-button" :class="{ 'is-stop': chatBusy }"
            :disabled="chatBusy ? pendingRun?.cancel_requested : !health || !question.trim() || submitting || uploading || activeJobs.length >= 3"
            :aria-label="t(chatBusy ? (pendingRun?.cancel_requested ? 'Stopping…' : 'Stop analysis') : 'Send message')"
            :title="t(chatBusy ? 'Stop analysis' : 'Send message')"
            @click="chatBusy ? stopJob(pendingRun) : send()">
            <Icon :name="chatBusy ? 'stop' : 'send'" :size="20" />
          </button>
        </div>
        <div v-if="uploading" class="upload-progress" role="status">
          <span>{{ uploadName }} · {{ progress }}% {{ progress === 100 ? '· reading file…' : '' }}</span>
          <progress :value="progress" max="100" aria-label="Upload progress"></progress>
        </div>
      </div>
    </section>
    </div>

    <dialog
      ref="drawer"
      class="drawer"
      :class="{ 'file-viewer': panel === 'inspect' }"
      @close="notificationHost = null"
      @click="$event.target === $event.currentTarget && drawer.close()"
    >
      <div class="drawer-header">
        <div>
          <h2>
            {{ t(
              panel === "sources"
                ? (sourceScope ? "Attached files" : "Your sources")
                : panel === "inspect"
                  ? "File viewer"
                  : panel === "steps"
                    ? "Next steps"
                    : panel === "account"
                      ? "Account"
                      : "Chat settings"
            ) }}
          </h2>
        </div>
        <button
          class="icon-button"
          aria-label="Close panel"
          @click="drawer.close()"
        >
          <Icon name="close" />
        </button>
      </div>
      <div class="drawer-body">
        <template v-if="panel === 'sources'">
          <button v-if="sourceScope" class="back-link" @click="openPanel('sources')"><Icon name="back" :size="16" /> All resources</button>
          <div class="source-toolbar">
            <button
              class="button primary"
              :disabled="uploading"
              @click="input.click()"
            >
              <Icon name="plus" :size="16" /> Upload files</button
            ><button class="quiet-button" @click="togglePM">{{ t(pmSelected ? 'Deselect PM flights' : 'Select PM flights') }}</button>
          </div>
          <input
            v-model="search"
            aria-label="Search source files"
            placeholder="Search a filename, altitude, or trial…"
          />
          <div class="filter-tabs">
            <button
              v-for="kind in ['all', 'pm', 'images', 'videos', 'other']"
              :key="kind"
              :class="{ active: filter === kind }"
              @click="filter = kind"
            >
              {{ t(kind) }}
            </button>
          </div>
          <div class="source-list">
            <div v-for="a in visibleAssets" :key="a.id" class="source-row">
              <input
                type="checkbox"
                :checked="selected.includes(a.id)"
                :disabled="!usable(a)"
                :aria-label="'Use ' + a.name + ' as evidence'"
                @change="toggle(a)"
              /><button class="source-info" @click="inspect(a)">
                <strong>{{ a.name }}</strong><span
                  >{{ a.role === "auto" ? a.kind : a.role }} · {{ size(a.bytes)
                  }}<span v-if="a.kind === 'table'">
                    · {{ number(a.info.rows) }} rows</span
                  ><span v-if="!usable(a)"> · stored only</span></span
                ></button
              ><button
                class="icon-button"
                :aria-label="'Delete ' + a.name"
                :disabled="resourceBusy(a.id)"
                @click="askDelete(a)"
              >
                <Icon name="trash" :size="17" />
              </button>
            </div>
            <p v-if="!visibleAssets.length" class="panel-copy">
              No matching sources. Upload a file to get started.
            </p>
          </div>
        </template>
        <template v-else-if="panel === 'inspect' && focused">
          <button class="back-link" @click="panel = 'sources'">
            <Icon name="back" :size="16" /> {{ t("All sources") }}
          </button>
          <h3 class="source-title">{{ focused.name }}</h3>
          <p class="panel-copy">
            Source {{ focused.id.slice(0, 8) }} · {{ size(focused.bytes) }}
            <span v-if="focused.info.crs">· {{ focused.info.crs }}</span>
          </p>
          <div
            v-if="['raster', 'image'].includes(focused.kind)"
            class="preview-area"
          >
            <div v-if="!previewFailed" class="image-stage" @click="pickCrop">
              <img
                :key="previewUrl"
                :src="previewUrl"
                :alt="'Preview of ' + focused.name"
                @error="previewFailed = true"
              />
              <div
                v-if="focused.kind === 'raster'"
                class="crop-outline"
                :style="selectionBox"
              ></div>
            </div>
            <p v-else class="panel-copy">
              Preview unavailable. Check the image bands or try reopening this file.
            </p>
          </div>
          <div v-if="focused.kind === 'video'" class="preview-area video-player">
            <video :key="focused.id" controls playsinline preload="metadata" :poster="previewUrl" :src="'/api/assets/' + focused.id + '/media'" :aria-label="'Video: ' + focused.name" @canplay="videoError = ''" @error="videoPlaybackError(focused.id)"></video>
            <p v-if="videoError" class="panel-copy" role="alert">{{ videoError }}</p>
          </div>
          <div v-if="focused.kind === 'raster'" class="crop-controls">
            <h3>Attach an analysis crop</h3>
            <p class="panel-copy">
              Click the preview to position a crop, or enter source-pixel
              coordinates. This is optional: attaching the original scans its full extent in tiles.
            </p>
            <div class="field-row">
              <label
                >X<input v-model.number="crop.x" type="number" min="0" /></label
              ><label
                >Y<input v-model.number="crop.y" type="number" min="0" /></label
              ><label
                >Width<input
                  v-model.number="crop.width"
                  type="number"
                  min="32"
                  max="4096" /></label
              ><label
                >Height<input
                  v-model.number="crop.height"
                  type="number"
                  min="32"
                  max="4096"
              /></label>
            </div>
            <label
              >Bands: one band or three RGB bands<input
                v-model="bandText"
                placeholder="Default: 1,2,3 or 1" /></label
            ><button
              class="button primary full-width"
              :disabled="savingCrop"
              @click="saveCrop"
            >
              {{ savingCrop ? "Saving crop…" : "Save and attach crop" }} <Icon name="check" :size="16" />
            </button>
            <p class="fine-print">
              Per-band display stretch is applied to non-uint8 data. This
              preview is not a calibrated DEM/DSM measurement.
            </p>
          </div>
          <div v-if="fileError" class="response-error" role="alert">{{ fileError }} <button class="quiet-button" :disabled="fileLoading" @click="loadFileContent(fileContent?.offset || 0)"><Icon name="refresh" :size="15" /> {{ t("Retry") }}</button></div>
          <p v-if="fileLoading" class="panel-copy" role="status">Loading file…</p>
          <template v-if="fileContent">
            <div v-if="fileContent.kind === 'table'" class="table-scroll file-rows" :aria-busy="fileLoading">
              <table><thead><tr><th v-for="column in fileContent.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in fileContent.rows" :key="index"><td v-for="column in fileContent.columns" :key="column">{{ row[column] ?? '—' }}</td></tr></tbody></table>
            </div>
            <pre v-else class="log-preview">{{ fileContent.text }}</pre>
            <div class="file-pagination">
              <span>{{ fileContent.kind === 'table' ? 'Rows' : 'Characters' }} {{ number(fileContent.offset + 1) }}–{{ number(fileContent.kind === 'table' ? fileContent.offset + fileContent.rows.length : fileContent.offset + fileContent.text.length) }} of {{ number(fileContent.total) }}</span>
              <button class="button" :disabled="fileLoading || fileContent.offset === 0" @click="loadFileContent(Math.max(0, fileContent.offset - (fileContent.kind === 'table' ? 100 : 12000)))"><Icon name="back" :size="15" /> {{ t("Previous") }}</button>
              <button class="button" :disabled="fileLoading || fileContent.next_offset === null" @click="loadFileContent(fileContent.next_offset)">{{ t("Next") }} <Icon name="forward" :size="15" /></button>
            </div>
          </template>
          <details v-if="focused.kind === 'table'" class="file-statistics"><summary>{{ t("Statistics") }}</summary>
          <template
            ><div class="dataset-summary">
              <strong>{{ number(focused.info.rows) }} measurements</strong
              ><span>{{ focused.info.time_range?.join(" → ") }}</span
              ><span v-if="focused.info.experiment"
                >Filename settings: speed
                {{ focused.info.experiment.speed_setting }}, altitude
                {{ focused.info.experiment.altitude_setting_m }} m, trial
                {{ focused.info.experiment.trial }}</span
              >
            </div>
            <div class="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Measurement</th>
                    <th>Min</th>
                    <th>Mean</th>
                    <th>Max</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(stats, name) in focused.info.statistics"
                    :key="name"
                  >
                    <td>{{ name }}</td>
                    <td>{{ number(stats.min) }}</td>
                    <td :title="stats.mean_method || 'Arithmetic mean'">
                      {{ number(stats.mean) }}
                    </td>
                    <td>{{ number(stats.max) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="fine-print">
              Units remain in column names. Means are per record; wind-direction
              means are circular. Filename altitude settings differ from
              measured altitude. Timezones are not inferred.
            </p></template>
          </details>
          <p v-if="!usable(focused)" class="panel-copy">
            Stored in its original format. Joblib execution and 3D measurements
            follow baseline evaluation.
          </p>
          <div class="source-toolbar">
            <button
              v-if="usable(focused) && focused.kind !== 'raster'"
              class="button primary"
              @click="toggle(focused)"
            >
              {{
                selected.includes(focused.id)
                  ? "Remove from next message"
                  : "Attach to next message"
              }}</button><a
              :href="'/api/assets/' + focused.id + '/file'"
              download
              >Original file <Icon name="download" :size="14" /></a
            >
          </div>
        </template>
        <template v-else-if="panel === 'account'">
          <div class="account-profile"><span class="account-avatar"><span v-if="profile.name">{{ profile.name[0].toUpperCase() }}</span><Icon v-else name="account" :size="26" /></span><div><strong>{{ profile.name || t('Your profile') }}</strong><p v-if="profile.role" class="panel-copy">{{ profile.role }}</p></div></div>
          <form @submit.prevent="saveProfile" class="profile-form">
            <label>{{ t("Name") }}<input v-model="profileName" maxlength="80" autocomplete="name" required placeholder="Your name" /></label>
            <label>{{ t("Role or team") }}<input v-model="profileRole" maxlength="80" autocomplete="organization-title" placeholder="Site engineer, safety team…" /></label>
            <button class="button primary" type="submit">{{ t("Save profile") }}</button>
            <p v-if="profileStatus" class="panel-copy" role="status">{{ profileStatus }}</p>
          </form>
          <button class="button full-width" @click="panel = 'settings'"><Icon name="settings" :size="17" /> {{ t('Settings') }}</button>
        </template>
        <template v-else-if="panel === 'settings'">
          <h3>{{ t("Model & connection") }}</h3>
          <p class="panel-copy">
            Qwen3-VL-4B-Instruct · {{ model?.backend || "transformers" }} · {{ model?.quantization || "NF4 4-bit" }} ·
            {{ model?.state || "offline" }}. The last three completed
            question/answer pairs accompany follow-ups.
          </p>
          <div class="source-toolbar">
            <button
              class="button primary"
              :disabled="
                !health ||
                submitting ||
                activeJobs.length > 0 ||
                model?.state !== 'unloaded'
              "
              @click="queue('load')"
            >
              {{ t(model?.backend === 'vllm' ? 'Connect vLLM' : 'Load Qwen') }}</button
            ><button
              v-if="model?.managed_gpu !== false"
              class="button"
              :disabled="
                !health ||
                submitting ||
                activeJobs.length > 0 ||
                model?.state !== 'loaded'
              "
              @click="queue('unload')"
            >
              {{ t("Release GPU") }}</button
            ><button class="quiet-button" @click="refresh"><Icon name="refresh" :size="16" /> {{ t("Reconnect") }}</button>
          </div>
          <p v-if="model?.backend === 'vllm'" class="panel-copy">Stop the vLLM server in its WSL terminal to release the GPU.</p>
          <div
            v-for="job in jobs
              .filter(
                (j) =>
                  j.request.action !== 'analyze' && j.status !== 'completed',
              )
              .slice(0, 2)"
            :key="job.id"
            class="model-job"
          >
            <strong>{{ job.request.action }} · {{ job.status }}</strong>
            <p>
              {{
                job.error ||
                "This may download the official checkpoint on first load."
              }}
            </p>
          </div>
          <h3>{{ t("Appearance") }}</h3>
          <div class="theme-options" role="group" aria-label="Color theme"><button :aria-pressed="theme === 'light'" @click="setTheme('light')"><Icon name="sun" :size="17" /> {{ t("Light") }}</button><button :aria-pressed="theme === 'dark'" @click="setTheme('dark')"><Icon name="moon" :size="17" /> {{ t("Dark") }}</button></div>
          <h3>{{ t("Inference budget") }}</h3>
          <div class="field-row">
            <label
              >{{ t("Image edge") }}<select v-model.number="imageEdge">
                <option :value="512">512 px</option>
                <option :value="768">768 px</option>
                <option :value="1024">1024 px</option>
                <option :value="1280">1280 px</option>
              </select></label
            ><label
              >{{ t("Output tokens") }}<select v-model.number="outputTokens">
                <option :value="384">384</option>
                <option :value="768">768</option>
                <option :value="1024">1024</option>
              </select></label
            >
          </div>
          <label>Orthophoto tile size<select v-model.number="tileEdge"><option :value="512">512 px · more detail</option><option :value="1024">1024 px</option><option :value="1536">1536 px</option><option :value="2048">2048 px · fewer tiles</option></select></label>
          <p class="fine-print">All image regions are processed. Larger tiles reduce scan time but can hide small objects after resizing. You can stop after the current batch.</p>
          <h3>{{ t("Video sampling") }}</h3>
          <div class="field-row">
            <label
              >Start (seconds)<input
                v-model.number="videoStart"
                type="number"
                min="0"
                step="0.1" /></label
            ><label
              >End (seconds)<input
                v-model="videoEnd"
                type="number"
                placeholder="Full recording"
                min="0.1"
                step="0.1" /></label
            ><label
              >Frames<select v-model.number="frameCount">
                <option :value="4">4</option>
                <option :value="8">8</option>
                <option :value="16">16</option>
                <option :value="32">32</option>
                <option :value="64">64</option>
                <option :value="120">120</option>
              </select></label
            >
          </div>
          <p class="fine-print">
            Videos can be up to 8 GiB. Leave the end blank to sample across the full recording. More samples improve temporal coverage but take longer. Audio is not analyzed; events between frames may be missed.
          </p>
          <h3>This conversation</h3>
          <button class="button" :disabled="reportBusy" @click="exportReport">
            <Icon name="download" :size="16" /> {{ reportBusy ? "Exporting…" : "Export evidence report" }}
          </button>
          <button class="quiet-button next-link" @click="panel = 'steps'">Project next steps <Icon name="arrow" :size="16" /></button>
        </template>
        <ol v-else-if="panel === 'steps'" class="next-steps">
          <li>
            <strong>Confirm the PM library</strong>
            <p>
              All {{ pmAssets.length }} imported flight CSVs are available in
              Sources. Ask for altitude/speed comparisons, peaks, filters, or
              correlations. Inspect the calculated evidence under a response.
            </p>
          </li>
          <li>
            <strong>Finish model setup</strong>
            <p>
              Load Qwen in Settings. If checkpoint downloads stall, complete the
              checkpoint download before running chat. The interface never
              substitutes generated demo answers.
            </p>
          </li>
          <li>
            <strong>Add visual evidence</strong>
            <p>
              Attach an orthophoto or a recorded video and ask about visible equipment or activities. Full image scans show progress. Videos use timestamped samples across the selected interval.
            </p>
          </li>
          <li>
            <strong>Build a checked baseline</strong>
            <p>
              Review answers against actual records and images. Hold out
              complete flights/days; record count errors, QA correctness,
              unsupported claims, latency, and GPU memory.
            </p>
          </li>
          <li>
            <strong>Optimize, then decide on QLoRA</strong>
            <p>
              Compare image resolution and frame budgets. Fine-tune only if
              repeated construction-specific errors remain. Joblib inference and
              calibrated 3D analyses are later additions.
            </p>
          </li>
        </ol>
      </div>
      <div v-if="panel === 'sources' && attachments.length" class="drawer-footer">
        <button class="button primary" @click="addSelectedToChat">{{ t('Add to chat') }}</button>
      </div>
    </dialog>
    <dialog ref="renameDialog" class="confirm-dialog" aria-label="Rename chat" @cancel="editingChat = null">
      <form @submit.prevent="saveChatName">
        <h3>Rename chat</h3>
        <input v-model="renameTitle" aria-label="Chat name" maxlength="120" autofocus autocomplete="off" />
        <p v-if="chatError" class="response-error" role="alert">{{ chatError }}</p>
        <div class="confirm-actions"><button type="button" class="button" :disabled="chatSaving" @click="renameDialog.close(); editingChat = null">{{ t("Cancel") }}</button><button type="submit" class="button primary" :disabled="chatSaving || !renameTitle.trim()">{{ chatSaving ? 'Saving…' : 'Save name' }}</button></div>
      </form>
    </dialog>
    <dialog ref="chatDeleteDialog" class="confirm-dialog" aria-label="Delete chat" @cancel="deletingChat = null">
      <h3>Delete this chat?</h3>
      <p>{{ chatTitle(deletingChat) }}</p>
      <p class="panel-copy">Its messages and saved analyses will be permanently deleted. Uploaded files are kept.</p>
      <p v-if="chatError" class="response-error" role="alert">{{ chatError }}</p>
      <div class="confirm-actions"><button class="button" :disabled="chatSaving" @click="chatDeleteDialog.close(); deletingChat = null">{{ t("Cancel") }}</button><button class="button danger" :disabled="chatSaving" @click="deleteChat"><Icon name="trash" :size="16" /> {{ chatSaving ? 'Deleting…' : 'Delete chat' }}</button></div>
    </dialog>
    <dialog ref="deleteDialog" class="confirm-dialog" @cancel="deleteTarget = null">
      <h3>Delete this resource?</h3>
      <p>{{ deleteTarget?.name }}</p>
      <p class="panel-copy">The local file will be removed permanently. Previous chat answers and saved source references remain available.</p>
      <p v-if="deleteError" class="response-error" role="alert">{{ deleteError }}</p>
      <div class="confirm-actions"><button class="button" :disabled="deleting" @click="deleteDialog.close(); deleteTarget = null">{{ t("Cancel") }}</button><button class="button danger" :disabled="deleting" @click="deleteResource">{{ deleting ? 'Deleting…' : 'Delete file' }}</button></div>
    </dialog>
  </div>
</template>

/* 智能周报系统 —— 原生 JS 单页应用
 * 登录 / 成员填报 / 主任看板与汇总 / 院领导查阅
 */
(() => {
  "use strict";

  const TOKEN_KEY = "swr_token";
  const CATEGORIES = ["done", "plan", "issue", "coord"];
  const CATEGORY_LABELS = { done: "完成", plan: "计划", issue: "问题", coord: "协调" };
  const AGENT_LABELS = { merger: "归并", validator: "校验", summarizer: "摘要", risk: "风险" };
  const ENGINE_LABELS = { llm: "大模型", rule: "规则引擎" };
  const MEMBER_CATEGORY_LABELS = {
    done: "本周完成工作",
    plan: "下周工作计划",
    issue: "存在问题",
    coord: "需协调事项",
  };
  const RISK_LABELS = {
    missing_submission: "未提交",
    unclosed_coord: "协调超期未闭环",
    stale_plan: "连续未推进",
  };
  const STATUS_CLASS = {
    草稿: "is-draft",
    已提交: "is-submitted",
    已退回: "is-returned",
    已汇总: "is-aggregated",
    已定稿: "is-finalized",
    已上报: "is-reported",
    未提交: "is-missing",
  };

  const state = {
    token: localStorage.getItem(TOKEN_KEY) || "",
    user: null,
    weeks: [],
    departments: [],
    engine: "rule",
    member: { report: null, weekId: null },
    director: { overview: null, report: null, weekId: null },
    leader: { reports: [], weekId: "", deptId: "" },
  };

  let pendingReturn = null;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const roleLabels = {
    member: "科室成员",
    director: "科室主任",
    leader: "院领导",
    admin: "系统管理员",
  };

  /* ---------------- 基础工具 ---------------- */

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => {
      const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
      return map[char];
    });
  }

  function formatTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("zh-CN", { hour12: false });
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(path, { ...options, headers });
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (error) {
        data = text;
      }
    }

    if (response.status === 401) {
      clearSession();
      showLogin("登录已失效，请重新登录");
      throw new Error("未登录或登录已失效");
    }
    if (!response.ok) {
      const message = (data && (data.detail || data.message)) || `请求失败（${response.status}）`;
      throw new Error(message);
    }
    return data;
  }

  function showToast(message, type = "info") {
    const container = $("#toast-container");
    const toast = document.createElement("div");
    toast.className = `toast is-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    window.setTimeout(() => toast.remove(), 3200);
  }

  function setBusy(button, busy, busyText = "处理中...") {
    if (!button) return;
    if (busy) {
      if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
      button.textContent = busyText;
      button.disabled = true;
    } else {
      if (button.dataset.originalText) {
        button.textContent = button.dataset.originalText;
        delete button.dataset.originalText;
      }
      button.disabled = false;
    }
  }

  function setStatusBadge(element, status) {
    element.className = `status-badge ${STATUS_CLASS[status] || ""}`;
    element.textContent = status;
  }

  function setSession(token, user) {
    state.token = token;
    state.user = user;
    localStorage.setItem(TOKEN_KEY, token);
  }

  function clearSession() {
    state.token = "";
    state.user = null;
    localStorage.removeItem(TOKEN_KEY);
    state.member = { report: null, weekId: null };
    state.director = { overview: null, report: null, weekId: null };
    state.leader = { reports: [], weekId: "", deptId: "" };
  }

  function showView(viewId) {
    $$(".view").forEach((view) => view.classList.toggle("active", view.id === viewId));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function showLogin(message = "") {
    $("#topbar").classList.add("hidden");
    showView("view-login");
    const errorBox = $("#login-error");
    if (message) {
      errorBox.textContent = message;
      errorBox.classList.remove("hidden");
    } else {
      errorBox.classList.add("hidden");
    }
  }

  /* ---------------- 登录与会话 ---------------- */

  async function doLogin(username, password) {
    const errorBox = $("#login-error");
    const loginButton = $("#login-btn");
    errorBox.classList.add("hidden");
    loginButton.disabled = true;
    loginButton.textContent = "登录中...";

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "用户名或密码错误");

      setSession(data.access_token, data.user);
      await enterApp();
      showToast(`欢迎，${data.user.name}`, "success");
    } catch (error) {
      errorBox.textContent = error.message || "登录失败";
      errorBox.classList.remove("hidden");
    } finally {
      loginButton.disabled = false;
      loginButton.textContent = "登 录";
    }
  }

  async function enterApp() {
    const user = state.user;
    $("#topbar").classList.remove("hidden");
    $("#current-user-name").textContent = user.name;
    $("#current-role").textContent = roleLabels[user.role] || user.role;

    await loadWeeks();

    if (user.role === "member") {
      showView("view-member");
      await loadMemberView();
    } else if (user.role === "director") {
      // 主任登录后显式落到上一周，避免依赖下拉框的初始化时序
      applyDirectorDefaultWeek();
      showView("view-director");
      await loadDirectorView();
    } else if (user.role === "leader") {
      showView("view-leader");
      await loadLeaderView();
    } else {
      showView("view-admin");
    }
  }

  async function restoreSession() {
    if (!state.token) {
      showLogin();
      return;
    }
    try {
      state.user = await api("/api/auth/me");
      await enterApp();
    } catch (error) {
      showLogin();
    }
  }

  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch (error) {
      // 忽略网络错误，本地会话照常清理
    }
    clearSession();
    showLogin();
    showToast("已退出登录", "info");
  }

  function applyDirectorDefaultWeek() {
    const select = $("#director-week");
    if (!select || !state.weeks.length) return;
    // 周次接口按新→旧返回；主任默认上一周，没有上一周时退回最新周
    const index = state.weeks.length > 1 ? 1 : 0;
    select.value = String(state.weeks[index].id);
  }

  async function loadWeeks() {
    try {
      state.weeks = (await api("/api/weeks")) || [];
    } catch (error) {
      showToast(error.message, "error");
      return;
    }

    const options = state.weeks
      .map(
        (week) =>
          `<option value="${week.id}">第 ${week.week_no} 周（${week.start_date} ~ ${week.end_date}）</option>`
      )
      .join("");

    $$("[data-week-select]").forEach((select) => {
      const includeAll = select.id === "leader-week";
      select.innerHTML = (includeAll ? '<option value="">全部周次</option>' : "") + options;

      if (!includeAll && state.weeks.length) {
        // 成员默认最新周（含空白填报周）；主任默认上一周，
        // 符合“周一/周二汇总上周周报”的实际工作节奏。
        const preferPrevious = select.dataset.defaultWeek === "previous";
        const index = preferPrevious && state.weeks.length > 1 ? 1 : 0;
        select.value = String(state.weeks[index].id);
      }
    });
  }

  /* ---------------- 成员填报 ---------------- */

  function memberWeekId() {
    const value = $("#member-week").value;
    return value ? Number(value) : null;
  }

  async function loadMemberView() {
    const weekId = memberWeekId();
    if (!weekId) {
      state.member.report = null;
      renderMemberView(null);
      return;
    }
    state.member.weekId = weekId;
    const editor = $("#member-editor");
    editor.classList.add("is-loading");
    try {
      const report = await api(`/api/member/report?week_id=${weekId}`);
      state.member.report = report;
      renderMemberView(report);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      editor.classList.remove("is-loading");
    }
  }

  function addMemberRow(category, value = "", focus = false) {
    const container = $(`#rows-${category}`);
    const row = document.createElement("div");
    row.className = "entry-row";

    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 300;
    input.value = value;
    input.placeholder = "请输入具体内容";

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn btn-ghost btn-small row-delete";
    remove.textContent = "删除";
    remove.addEventListener("click", () => {
      row.remove();
      if (!container.querySelector(".entry-row") && state.member.report?.status !== "已提交") {
        addMemberRow(category, "", true);
      }
    });

    row.append(input, remove);
    container.appendChild(row);
    if (focus) input.focus();
    syncMemberControls();
  }

  function syncMemberControls() {
    const status = state.member.report?.status;
    const submitted = status === "已提交";
    const returned = status === "已退回";

    $$("#member-editor input").forEach((input) => {
      input.disabled = submitted;
    });
    $$("#member-editor [data-add-row], #member-editor .row-delete").forEach((button) => {
      button.disabled = submitted;
    });
    $("#member-save").disabled = submitted;
    $("#member-submit").disabled = submitted;
    $("#member-submit").textContent = returned ? "重新提交" : "提交周报";

    if (submitted) {
      $("#member-hint").textContent = "周报已提交并锁定；如需修改请联系主任退回";
    } else if (returned) {
      $("#member-hint").textContent = "请根据退回理由修改后重新提交";
    } else {
      $("#member-hint").textContent = "提交后内容锁定，主任退回后可再次编辑";
    }
  }

  function renderMemberView(report) {
    state.member.report = report;
    const status = report ? report.status : "未填写";
    setStatusBadge($("#member-status"), status);
    const submitted = status === "已提交";
    const returned = status === "已退回";
    const banner = $("#member-return-banner");

    if (returned) {
      banner.classList.remove("hidden");
      $("#member-return-reason").textContent = report.return_reason || "（未填写理由）";
    } else {
      banner.classList.add("hidden");
    }

    CATEGORIES.forEach((category) => {
      const container = $(`#rows-${category}`);
      container.innerHTML = "";
      const values = report ? report[category] || [] : [];
      if (values.length) {
        values.forEach((value) => addMemberRow(category, value, false));
      } else if (!submitted) {
        addMemberRow(category, "", false);
      }
    });

    syncMemberControls();
  }

  function collectMemberItems() {
    const data = {};
    CATEGORIES.forEach((category) => {
      data[category] = $$(`#rows-${category} input`)
        .map((input) => input.value.trim())
        .filter(Boolean);
    });
    return data;
  }

  async function saveMemberDraft({ silent = false } = {}) {
    const weekId = memberWeekId();
    if (!weekId) {
      showToast("请先选择周次", "error");
      return null;
    }
    const button = $("#member-save");
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "保存中...";
    try {
      const report = await api("/api/member/report/draft", {
        method: "POST",
        body: JSON.stringify({ week_id: weekId, ...collectMemberItems() }),
      });
      state.member.report = report;
      renderMemberView(report);
      if (!silent) showToast("草稿已保存", "success");
      return report;
    } catch (error) {
      showToast(error.message, "error");
      return null;
    } finally {
      button.textContent = label;
      syncMemberControls();
    }
  }

  async function submitMemberReport() {
    const weekId = memberWeekId();
    if (!weekId) return;
    const button = $("#member-submit");
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "提交中...";
    try {
      const saved = await saveMemberDraft({ silent: true });
      if (!saved) return;

      const report = await api("/api/member/report/submit", {
        method: "POST",
        body: JSON.stringify({ week_id: weekId }),
      });
      state.member.report = report;
      renderMemberView(report);
      showToast("周报已提交并锁定", "success");
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      button.textContent = label;
      syncMemberControls();
    }
  }

  /* ---------------- 主任看板与汇总 ---------------- */

  function directorWeekId() {
    const value = $("#director-week").value;
    return value ? Number(value) : null;
  }

  async function loadDirectorView() {
    const weekId = directorWeekId();
    if (!weekId) {
      state.director.overview = null;
      state.director.report = null;
      renderDirectorOverview(null);
      renderDirectorReport(null);
      return;
    }
    state.director.weekId = weekId;
    $("#overview-list").innerHTML = '<p class="empty">加载中...</p>';
    try {
      const [overview, report] = await Promise.all([
        api(`/api/director/overview?week_id=${weekId}`),
        api(`/api/director/dept-report?week_id=${weekId}`),
      ]);
      state.director.overview = overview;
      state.director.report = report;
      renderDirectorOverview(overview);
      renderDirectorReport(report);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function renderDirectorOverview(overview) {
    if (!overview) {
      $("#stat-submitted").textContent = "-";
      $("#stat-missing").textContent = "-";
      $("#stat-missing-names").textContent = "-";
      $("#overview-list").innerHTML = '<p class="empty">暂无数据</p>';
      return;
    }

    $("#stat-submitted").textContent = overview.submitted_count;
    $("#stat-missing").textContent = overview.missing_count;
    $("#stat-missing-names").textContent = (overview.missing_names || []).length
      ? overview.missing_names.join("、")
      : "无";

    const canReturn = state.director.report?.status === "已汇总";
    $("#overview-list").innerHTML =
      (overview.members || [])
        .map((member) => {
          const submitted = member.status === "已提交";
          const classes = submitted ? "member-card is-submitted" : "member-card is-missing";
          const time = member.submitted_at ? ` · ${formatTime(member.submitted_at)}` : "";
          const returnButton =
            submitted && canReturn
              ? `<div class="member-card-actions">
                   <button class="btn btn-ghost btn-small" type="button"
                     data-return-member="${member.report_id}"
                     data-member-name="${escapeHtml(member.name)}">退回</button>
                 </div>`
              : "";
          return `<article class="${classes}">
            <div class="member-card-name">${escapeHtml(member.name)}</div>
            <div class="member-card-status">${escapeHtml(member.status)}${time}</div>
            ${returnButton}
          </article>`;
        })
        .join("") || '<p class="empty">暂无成员</p>';

    $$("[data-return-member]").forEach((button) => {
      button.addEventListener("click", () => {
        openReturnModal(Number(button.dataset.returnMember), button.dataset.memberName || "该成员");
      });
    });
  }

  function syncDirectorControls() {
    const status = state.director.report?.status;
    const aggregated = status === "已汇总";
    const returned = status === "已退回";

    const aggregateButton = $("#aggregate-btn");
    aggregateButton.disabled = Boolean(status) && !returned;
    aggregateButton.textContent = returned ? "重新汇总" : "一键汇总";
    $("#finalize-btn").disabled = !aggregated;
    $("#report-btn").disabled = status !== "已定稿";
    $("#add-item-btn").disabled = !aggregated;
    if (!aggregated) $("#add-item-row").classList.add("hidden");

    const hints = {
      已汇总: "可直接双击条目/摘要修改；确认无误后定稿",
      已定稿: "已定稿，编辑区已锁定；可上报院领导",
      已上报: "已上报院领导，汇总内容只读",
      已退回: "已有成员被退回，请等待重提后重新汇总",
    };
    $("#director-hint").textContent = hints[status] || "汇总后可在本页编辑条目并定稿上报";
  }

  function mergedItemHtml(item, index, editable) {
    const sources = (item.source_names || [])
      .map((name) => `<span class="source-badge">${escapeHtml(name)}</span>`)
      .join("");
    const actions = editable
      ? `<div class="item-actions">
           <button class="btn btn-ghost btn-small" type="button" data-delete-item="${index}">删除</button>
         </div>`
      : "";
    return `<div class="merged-item" data-index="${index}">
      <span class="category-tag">${escapeHtml(CATEGORY_LABELS[item.category] || item.category)}</span>
      <div class="merged-content" data-role="content"${editable ? ' title="双击编辑"' : ""}>${escapeHtml(item.content)}</div>
      <div class="source-badges">${sources}</div>
      ${actions}
    </div>`;
  }

  function traceHtml(traces, emptyText = "尚无 trace") {
    if (!traces || !traces.length) {
      return `<span class="trace-badge">${escapeHtml(emptyText)}</span>`;
    }
    return traces
      .map((trace) => {
        const degraded = trace.status === "degraded";
        const label = `${AGENT_LABELS[trace.agent] || trace.agent}：${
          ENGINE_LABELS[trace.engine] || trace.engine
        }${degraded ? "（降级）" : ""}`;
        const title = trace.detail ? ` title="${escapeHtml(trace.detail)}"` : "";
        return `<span class="trace-badge${degraded ? " is-degraded" : ""}"${title}>${escapeHtml(label)}</span>`;
      })
      .join("");
  }

  function renderChecked(items) {
    const container = $("#director-checked");
    if (!items.length) {
      container.innerHTML = '<p class="empty">暂无校验建议</p>';
      return;
    }
    container.innerHTML = items
      .map((item) => {
        const sourceBadges = (item.source_names || [])
          .map((name) => `<span class="source-badge">${escapeHtml(name)}</span>`)
          .join("");
        const sourceLine = sourceBadges
          ? `<p class="issue-source">来源：${sourceBadges}</p>`
          : '<p class="issue-source">来源：未记录</p>';
        const issues = (item.issues || []).map((issue) => `<p>· ${escapeHtml(issue)}</p>`).join("");
        const suggestions = (item.suggestions || [])
          .map((suggestion) => `<p>建议：${escapeHtml(suggestion)}</p>`)
          .join("");
        return `<div class="issue-item">
          <strong>${escapeHtml(item.content || "")}</strong>
          ${sourceLine}
          ${issues}
          ${suggestions}
        </div>`;
      })
      .join("");
  }

  function renderRisks(items) {
    const container = $("#director-risks");
    if (!items.length) {
      container.innerHTML = '<p class="empty">暂无风险提示</p>';
      return;
    }
    container.innerHTML = items
      .map((item) => {
        const label = RISK_LABELS[item.type] || item.type;
        const who = item.user_name ? ` · ${escapeHtml(item.user_name)}` : "";
        return `<div class="risk-item"><strong>${escapeHtml(label)}${who}</strong><p>${escapeHtml(
          item.detail || ""
        )}</p></div>`;
      })
      .join("");
  }

  function renderDirectorReport(report) {
    state.director.report = report;
    const status = report?.status || "未汇总";
    setStatusBadge($("#director-status"), status);
    const editable = status === "已汇总";

    const summary = $("#director-summary");
    summary.textContent = report?.summary || "尚未汇总";
    summary.classList.toggle("empty", !report?.summary);
    summary.ondblclick = editable ? startSummaryEdit : null;
    summary.title = editable ? "双击编辑摘要" : "";

    const itemsContainer = $("#director-items");
    if (!report || !report.items || !report.items.length) {
      itemsContainer.innerHTML = '<p class="empty">尚未汇总</p>';
    } else {
      itemsContainer.innerHTML = report.items
        .map((item, index) => mergedItemHtml(item, index, editable))
        .join("");
      if (editable) {
        $$(".merged-item", itemsContainer).forEach((row) => {
          const index = Number(row.dataset.index);
          row.querySelector("[data-role='content']")?.addEventListener("dblclick", () => startItemEdit(index));
          row.querySelector("[data-delete-item]")?.addEventListener("click", () => deleteDirectorItem(index));
        });
      }
    }

    renderChecked(report?.checked || []);
    renderRisks(report?.risks || []);
    $("#trace-badges").innerHTML = traceHtml(report?.engine_trace || [], "尚无 trace");
    syncDirectorControls();
  }

  async function aggregateDirector() {
    const weekId = directorWeekId();
    if (!weekId) return;
    const button = $("#aggregate-btn");
    setBusy(button, true, "汇总中...");
    try {
      const report = await api("/api/director/aggregate", {
        method: "POST",
        body: JSON.stringify({ week_id: weekId, engine_switch: state.engine }),
      });
      state.director.report = report;
      renderDirectorOverview(state.director.overview);
      renderDirectorReport(report);
      showToast("一键汇总完成", "success");
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setBusy(button, false);
      syncDirectorControls();
    }
  }

  async function persistDirectorItems(items) {
    const report = state.director.report;
    if (!report) return;
    const payload = items.map((item) => ({
      id: item.id || null,
      category: item.category,
      content: item.content,
      source_user_ids: item.source_user_ids || [],
      source_names: item.source_names || [],
    }));
    try {
      const updated = await api(`/api/director/dept-report/${report.id}/items`, {
        method: "PUT",
        body: JSON.stringify({ items: payload }),
      });
      state.director.report = updated;
      renderDirectorReport(updated);
      showToast("条目已更新", "success");
    } catch (error) {
      showToast(error.message, "error");
      renderDirectorReport(state.director.report);
    }
  }

  function startItemEdit(index) {
    const report = state.director.report;
    if (!report || report.status !== "已汇总") return;
    const item = report.items[index];
    const contentEl = document.querySelector(
      `.merged-item[data-index="${index}"] [data-role="content"]`
    );
    if (!item || !contentEl) return;

    const input = document.createElement("input");
    input.type = "text";
    input.className = "inline-input";
    input.maxLength = 300;
    input.value = item.content;
    contentEl.replaceWith(input);
    input.focus();
    input.select();

    let finished = false;
    const finish = async (save) => {
      if (finished) return;
      finished = true;
      const value = input.value.trim();
      if (!save || !value || value === item.content) {
        renderDirectorReport(state.director.report);
        return;
      }
      await persistDirectorItems(
        report.items.map((current, currentIndex) =>
          currentIndex === index ? { ...current, content: value } : current
        )
      );
    };

    input.addEventListener("blur", () => finish(true));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        input.blur();
      } else if (event.key === "Escape") {
        event.preventDefault();
        finish(false);
      }
    });
  }

  async function deleteDirectorItem(index) {
    const report = state.director.report;
    if (!report || report.status !== "已汇总") return;
    const item = report.items[index];
    if (!item) return;
    if (!window.confirm(`确定删除条目“${item.content}”？`)) return;
    await persistDirectorItems(report.items.filter((_, currentIndex) => currentIndex !== index));
  }

  function startSummaryEdit() {
    const report = state.director.report;
    if (!report || report.status !== "已汇总") return;
    const element = $("#director-summary");
    const original = report.summary || "";
    element.contentEditable = "true";
    element.focus();

    element.onkeydown = (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        element.blur();
      } else if (event.key === "Escape") {
        element.textContent = original;
        element.blur();
      }
    };
    element.onblur = async () => {
      element.contentEditable = "false";
      element.onkeydown = null;
      element.onblur = null;
      const value = element.textContent.trim();
      if (value === original) {
        renderDirectorReport(state.director.report);
        return;
      }
      try {
        const updated = await api(`/api/director/dept-report/${report.id}/summary`, {
          method: "PUT",
          body: JSON.stringify({ summary: value }),
        });
        state.director.report = updated;
        renderDirectorReport(updated);
        showToast("摘要已更新", "success");
      } catch (error) {
        showToast(error.message, "error");
        renderDirectorReport(state.director.report);
      }
    };
  }

  function openAddItemRow() {
    if (state.director.report?.status !== "已汇总") return;
    $("#add-item-row").classList.remove("hidden");
    $("#add-item-content").focus();
  }

  function closeAddItemRow() {
    $("#add-item-row").classList.add("hidden");
    $("#add-item-content").value = "";
  }

  async function confirmAddItem() {
    const report = state.director.report;
    if (!report || report.status !== "已汇总") return;
    const content = $("#add-item-content").value.trim();
    if (!content) {
      showToast("请输入条目内容", "error");
      return;
    }
    await persistDirectorItems([
      ...report.items,
      {
        category: $("#add-item-category").value,
        content,
        source_user_ids: [],
        source_names: [],
      },
    ]);
    closeAddItemRow();
  }

  function renderReturnPreview(report) {
    const groups = CATEGORIES.map((category) => {
      const items = report[category] || [];
      const body = items.length
        ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
        : '<p class="return-preview-empty">（未填写）</p>';
      return `<section class="return-preview-group">
        <h4>${MEMBER_CATEGORY_LABELS[category]}</h4>
        ${body}
      </section>`;
    }).join("");

    const submitted = report.submitted_at
      ? ` · 提交于 ${formatTime(report.submitted_at)}`
      : "";
    const meta = `状态：${escapeHtml(report.status)} · 版本 v${report.version}${submitted}`;
    $("#return-preview").innerHTML = `<p class="return-preview-meta">${meta}</p>${groups}`;
  }

  async function openReturnModal(memberReportId, memberName) {
    const report = state.director.report;
    if (!report || report.status !== "已汇总") {
      showToast("请先汇总后再退回成员周报", "error");
      return;
    }

    const request = { deptReportId: report.id, memberReportId, memberName };
    pendingReturn = request;
    $("#modal-subtitle").textContent = `将退回 ${memberName} 的周报，成员修改后可重新提交。`;
    $("#modal-reason").value = "";
    $("#return-preview").innerHTML =
      '<p class="return-preview-empty">正在加载成员原始周报...</p>';
    $("#modal-confirm").disabled = true;
    $("#modal-backdrop").classList.remove("hidden");

    try {
      const memberReport = await api(`/api/director/member-report/${memberReportId}`);
      if (pendingReturn !== request) return; // 弹窗已关闭或切换
      renderReturnPreview(memberReport);
    } catch (error) {
      if (pendingReturn !== request) return;
      $("#return-preview").innerHTML =
        `<p class="form-error">原始周报加载失败：${escapeHtml(error.message)}</p>`;
      showToast(error.message, "error");
    } finally {
      if (pendingReturn === request) {
        $("#modal-confirm").disabled = false;
        $("#modal-reason").focus();
      }
    }
  }

  function closeReturnModal() {
    pendingReturn = null;
    $("#modal-backdrop").classList.add("hidden");
  }

  async function confirmReturn() {
    if (!pendingReturn) return;
    const reason = $("#modal-reason").value.trim();
    if (!reason) {
      showToast("请填写退回理由", "error");
      return;
    }
    const button = $("#modal-confirm");
    setBusy(button, true, "退回中...");
    try {
      await api(`/api/director/dept-report/${pendingReturn.deptReportId}/return`, {
        method: "POST",
        body: JSON.stringify({
          member_report_id: pendingReturn.memberReportId,
          reason,
        }),
      });
      closeReturnModal();
      await loadDirectorView();
      showToast("已退回成员周报", "success");
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  }

  async function finalizeDirector() {
    const report = state.director.report;
    if (!report || report.status !== "已汇总") return;
    const button = $("#finalize-btn");
    setBusy(button, true, "定稿中...");
    try {
      const updated = await api(`/api/director/dept-report/${report.id}/finalize`, {
        method: "POST",
      });
      state.director.report = updated;
      renderDirectorOverview(state.director.overview);
      renderDirectorReport(updated);
      showToast("汇总稿已定稿", "success");
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setBusy(button, false);
      syncDirectorControls();
    }
  }

  async function reportDirector() {
    const report = state.director.report;
    if (!report || report.status !== "已定稿") return;
    const button = $("#report-btn");
    setBusy(button, true, "上报中...");
    try {
      const updated = await api(`/api/director/dept-report/${report.id}/report`, {
        method: "POST",
      });
      state.director.report = updated;
      renderDirectorOverview(state.director.overview);
      renderDirectorReport(updated);
      showToast("已上报院领导", "success");
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setBusy(button, false);
      syncDirectorControls();
    }
  }

  /* ---------------- 院领导查阅 ---------------- */

  async function loadDepartments() {
    if (state.departments.length) return;
    try {
      state.departments = (await api("/api/departments")) || [];
    } catch (error) {
      state.departments = [];
    }
    const select = $("#leader-dept");
    const current = select.value;
    select.innerHTML =
      '<option value="">全部科室</option>' +
      state.departments
        .map((department) => `<option value="${department.id}">${escapeHtml(department.name)}</option>`)
        .join("");
    select.value = current;
  }

  async function loadLeaderView() {
    await loadDepartments();
    const weekId = $("#leader-week").value;
    const deptId = $("#leader-dept").value;
    state.leader.weekId = weekId;
    state.leader.deptId = deptId;

    const container = $("#leader-reports");
    container.innerHTML = '<p class="empty">加载中...</p>';
    const params = new URLSearchParams();
    if (weekId) params.set("week_id", weekId);
    if (deptId) params.set("dept_id", deptId);

    try {
      const reports = await api(
        `/api/leader/reports${params.toString() ? `?${params.toString()}` : ""}`
      );
      state.leader.reports = (reports || []).filter((report) => report.status === "已上报");
      renderLeaderReports(state.leader.reports);
    } catch (error) {
      showToast(error.message, "error");
      container.innerHTML = '<p class="empty">加载失败，请稍后重试</p>';
    }
  }

  function mergedReadonlyHtml(item) {
    const sources = (item.source_names || [])
      .map((name) => `<span class="source-badge">${escapeHtml(name)}</span>`)
      .join("");
    return `<div class="merged-item">
      <span class="category-tag">${escapeHtml(CATEGORY_LABELS[item.category] || item.category)}</span>
      <div class="merged-content">${escapeHtml(item.content)}</div>
      <div class="source-badges">${sources}</div>
    </div>`;
  }

  function renderLeaderReports(reports) {
    const container = $("#leader-reports");
    if (!reports.length) {
      container.innerHTML = '<p class="empty">暂无已上报周报</p>';
      return;
    }
    container.innerHTML = reports
      .map((report) => {
        const items = (report.items || []).map(mergedReadonlyHtml).join("");
        return `<article class="leader-card">
          <div class="leader-card-head">
            <div>
              <h3>${escapeHtml(report.dept_name || "科室")} · 第 ${report.week_no} 周</h3>
              <p class="leader-card-meta">上报时间：${formatTime(report.reported_at)}</p>
            </div>
            <span class="status-badge is-reported">已上报</span>
          </div>
          <section class="summary-block">
            <h4>科室摘要</h4>
            <p class="summary-text">${escapeHtml(report.summary || "暂无摘要")}</p>
          </section>
          <section class="items-block">
            <h4>归并条目</h4>
            <div class="merged-items">${items || '<p class="empty">暂无条目</p>'}</div>
          </section>
          <div class="trace-badges">${traceHtml(report.engine_trace || [], "无 trace")}</div>
        </article>`;
      })
      .join("");
  }

  /* ---------------- 事件绑定 ---------------- */

  function bindEvents() {
    $("#login-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const username = $("#login-username").value.trim();
      const password = $("#login-password").value;
      if (!username || !password) {
        const errorBox = $("#login-error");
        errorBox.textContent = "请输入用户名和密码";
        errorBox.classList.remove("hidden");
        return;
      }
      doLogin(username, password);
    });

    $$(".account-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const username = chip.dataset.username;
        $("#login-username").value = username;
        $("#login-password").value = "demo123";
        doLogin(username, "demo123");
      });
    });

    $("#logout-btn").addEventListener("click", logout);

    $$("#engine-switch button").forEach((button) => {
      button.addEventListener("click", () => {
        state.engine = button.dataset.engine;
        $$("#engine-switch button").forEach((item) =>
          item.classList.toggle("active", item === button)
        );
      });
    });

    $("#member-week").addEventListener("change", loadMemberView);
    $("#director-week").addEventListener("change", loadDirectorView);
    $("#leader-week").addEventListener("change", loadLeaderView);
    $("#leader-dept").addEventListener("change", loadLeaderView);

    $$("[data-add-row]").forEach((button) => {
      button.addEventListener("click", () => addMemberRow(button.dataset.addRow, "", true));
    });
    $("#member-save").addEventListener("click", () => saveMemberDraft({ silent: false }));
    $("#member-submit").addEventListener("click", submitMemberReport);

    $("#aggregate-btn").addEventListener("click", aggregateDirector);
    $("#finalize-btn").addEventListener("click", finalizeDirector);
    $("#report-btn").addEventListener("click", reportDirector);
    $("#add-item-btn").addEventListener("click", openAddItemRow);
    $("#add-item-cancel").addEventListener("click", closeAddItemRow);
    $("#add-item-confirm").addEventListener("click", confirmAddItem);
    $("#add-item-content").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        confirmAddItem();
      }
    });

    $("#modal-cancel").addEventListener("click", closeReturnModal);
    $("#modal-confirm").addEventListener("click", confirmReturn);
    $("#modal-backdrop").addEventListener("click", (event) => {
      if (event.target === event.currentTarget) closeReturnModal();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeReturnModal();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    restoreSession();
  });
})();

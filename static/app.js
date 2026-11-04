/* 智能周报系统 —— 原生 JS 单页应用
 * 当前阶段：页面骨架 + 登录 + 角色路由；填报/汇总视图逻辑在下一阶段接入。
 */
(() => {
  "use strict";

  const TOKEN_KEY = "swr_token";

  const state = {
    token: localStorage.getItem(TOKEN_KEY) || "",
    user: null,
    weeks: [],
    currentWeekId: null,
    engine: "rule",
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const roleLabels = {
    member: "科室成员",
    director: "科室主任",
    leader: "院领导",
    admin: "系统管理员",
  };

  /* ---------------- 基础工具 ---------------- */

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (state.token) {
      headers.set("Authorization", `Bearer ${state.token}`);
    }
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
      const message =
        (data && (data.detail || data.message)) || `请求失败（${response.status}）`;
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
    window.setTimeout(() => {
      toast.remove();
    }, 3200);
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
      if (!response.ok) {
        throw new Error(data.detail || "用户名或密码错误");
      }

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

    const views = {
      member: "view-member",
      director: "view-director",
      leader: "view-leader",
      admin: "view-admin",
    };
    showView(views[user.role] || "view-login");
  }

  async function restoreSession() {
    if (!state.token) {
      showLogin();
      return;
    }
    try {
      const user = await api("/api/auth/me");
      state.user = user;
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

  /* ---------------- 元数据 ---------------- */

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
        select.value = String(state.weeks[0].id);
      }
    });

    if (state.weeks.length) {
      state.currentWeekId = Number(state.weeks[0].id);
    }
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

    // AI 引擎开关
    $$("#engine-switch button").forEach((button) => {
      button.addEventListener("click", () => {
        state.engine = button.dataset.engine;
        $$("#engine-switch button").forEach((item) =>
          item.classList.toggle("active", item === button)
        );
      });
    });

    // 周次切换（具体视图逻辑下一阶段接入）
    $$("[data-week-select]").forEach((select) => {
      select.addEventListener("change", () => {
        if (select.value) {
          state.currentWeekId = Number(select.value);
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    restoreSession();
  });
})();
